import asyncio
import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import select

from app.core.ai_settings import AiConfigurationError, load_chat_settings
from app.core.security import CurrentUser, DbSession
from app.integrations.chat import ChatClient, ChatError
from app.integrations.embeddings import EmbeddingClient, EmbeddingError
from app.integrations.hybrid_index import IndexNotReady
from app.models import AssistanceRun, KnowledgeDocument, Ticket, TicketCategory
from app.modules.analysis.assistance_schemas import (
    AdoptRequest,
    AssistanceDraft,
    AssistanceView,
    RankedSources,
    SourceSnapshot,
)
from app.modules.analysis.cases import case_fingerprint
from app.modules.analysis.router import RetrievalConfig, get_embedding_client, similar_cases
from app.modules.knowledge.search import search_knowledge
from app.modules.knowledge.text import document_fingerprint
from app.modules.tickets.service import add_record, get_ticket, lock_ticket

router = APIRouter(prefix="/api/tickets", tags=["AI处理建议"])
PROMPT_VERSION = "assistance-v1"


def get_chat_client():
    try:
        settings = load_chat_settings()
    except (ValidationError, AiConfigurationError) as error:
        raise HTTPException(503, str(error) if isinstance(error, AiConfigurationError) else '聊天模型配置错误') from error
    with ChatClient(
        str(settings.chat_base_url), settings.chat_api_key.get_secret_value(), settings.chat_model
    ) as client:
        yield client


ChatModel = Annotated[ChatClient, Depends(get_chat_client)]
EmbeddingModel = Annotated[EmbeddingClient, Depends(get_embedding_client)]


async def check_sources(db, sources: list[SourceSnapshot], *, lock=False):
    for source in sorted(sources, key=lambda item: (item.kind, item.entity_id)):
        if source.kind == "ticket":
            query = select(Ticket).where(Ticket.id == source.entity_id)
            case = await db.scalar(query.with_for_update() if lock else query)
            valid = (
                case is not None
                and case.status in {"resolved", "closed"}
                and bool(case.solution.strip())
                and case_fingerprint(case) == source.fingerprint
            )
        else:
            query_document = select(KnowledgeDocument).where(KnowledgeDocument.id == source.entity_id)
            document = await db.scalar(query_document.with_for_update() if lock else query_document)
            valid = (
                document is not None
                and document.status == "published"
                and document_fingerprint(document) == source.fingerprint
            )
        if not valid:
            raise HTTPException(409, "引用依据已变化或停用，请重建索引后重新生成建议")


@router.post("/{ticket_id}/assist", response_model=AssistanceView, status_code=201)
async def generate_assistance(
    ticket_id: int, db: DbSession, user: CurrentUser, config: RetrievalConfig, model: EmbeddingModel, chat: ChatModel
):
    started = time.monotonic()
    ticket = await get_ticket(db, ticket_id)
    if ticket.status not in {"pending", "processing"}:
        raise HTTPException(409, "只有待处理或处理中工单可以生成新的建议")
    author_id = user.id
    ticket_fingerprint = case_fingerprint(ticket)
    query = {"title": ticket.title, "description": ticket.description[:3000]}
    categories = [
        {"id": item.id, "name": item.name}
        for item in (await db.scalars(select(TicketCategory).where(TicketCategory.is_active)))
    ]
    try:
        cases = await similar_cases(ticket_id, db, user, config, model)
        knowledge = await search_knowledge(ticket, db, config, model)
        candidates = []
        for item in cases.items:
            case = await db.get(Ticket, item.id)
            if case is None:
                raise HTTPException(409, "参考案例已变化，请重新生成")
            candidates.append(
                SourceSnapshot(
                    source_id=f"T{case.id}",
                    kind="ticket",
                    entity_id=case.id,
                    title=f"{case.number} · {case.title}",
                    content=f"{case.description[:1500]}\n解决方案：{case.solution[:3000]}",
                    fingerprint=case_fingerprint(case),
                )
            )
        for item in knowledge.items:
            candidates.append(
                SourceSnapshot(
                    source_id=f"K{item.chunk_id}",
                    kind="knowledge",
                    entity_id=item.document_id,
                    title=f"{item.title} · 第{item.chunk_order}块",
                    content=item.content,
                    fingerprint=item.fingerprint,
                )
            )
        if not candidates:
            raise HTTPException(409, "没有有效参考依据；请先发布知识或准备有效案例并建立索引")
        # 检索结果已经成为普通数据，等待模型时释放数据库连接。
        await db.rollback()
        ranked = await asyncio.to_thread(
            chat.ask,
            "按与当前问题的相关性重排来源ID，只选有帮助的最多5条，不重复。",
            {"ticket": query, "sources": [source.model_dump() for source in candidates]},
            RankedSources,
        )
        by_id = {source.source_id: source for source in candidates}
        if len(set(ranked.source_ids)) != len(ranked.source_ids) or not set(ranked.source_ids) <= by_id.keys():
            raise ChatError("模型重排返回重复或不存在的来源ID")
        sources = [by_id[source_id] for source_id in ranked.source_ids]
        draft = await asyncio.to_thread(
            chat.ask,
            "根据提供的依据生成待人工核实的处理建议。category_id只能选categories中的id。"
            "P1整体中断，P2关键功能受阻，P3局部异常，P4咨询。每步必须引用source_ids。"
            "风险和待确认信息如实列出，没有则空列表；回复是草稿，不声称已执行修复或已发邮件。",
            {"ticket": query, "categories": categories, "sources": [source.model_dump() for source in sources]},
            AssistanceDraft,
        )
        if draft.category_id not in {category["id"] for category in categories}:
            raise ChatError("模型建议的分类不在当前启用分类中")
        allowed = set(ranked.source_ids)
        if any(
            not set(step.source_ids) <= allowed or len(step.source_ids) != len(set(step.source_ids))
            for step in draft.steps
        ):
            raise ChatError("模型建议引用了不存在或重复的来源ID")
    except IndexNotReady as error:
        raise HTTPException(503, str(error)) from error
    except (ChatError, EmbeddingError) as error:
        raise HTTPException(502, str(error)) from error
    # 网络调用期间不持有写锁；完成后重新读取，阻止把过期输入当成本次建议。
    current = await lock_ticket(db, ticket_id)
    if case_fingerprint(current) != ticket_fingerprint or current.status not in {"pending", "processing"}:
        raise HTTPException(409, "工单在生成期间已变化，请重新生成")
    await check_sources(db, sources, lock=True)
    run = AssistanceRun(
        ticket_id=ticket_id,
        author_id=author_id,
        ticket_fingerprint=ticket_fingerprint,
        draft=draft.model_dump(),
        sources=[source.model_dump() for source in sources],
        model=chat.model,
        prompt_version=PROMPT_VERSION,
        duration_ms=round((time.monotonic() - started) * 1000),
    )
    db.add(run)
    await db.commit()
    return run


@router.get("/{ticket_id}/assistance", response_model=list[AssistanceView])
async def assistance_history(ticket_id: int, db: DbSession, user: CurrentUser, page: Annotated[int, Query(ge=1)] = 1):
    await get_ticket(db, ticket_id)
    return (
        await db.scalars(
            select(AssistanceRun)
            .where(AssistanceRun.ticket_id == ticket_id)
            .order_by(AssistanceRun.id.desc())
            .offset((page - 1) * 10)
            .limit(10)
        )
    ).all()


@router.post("/{ticket_id}/assistance/{run_id}/adopt", response_model=AssistanceView)
async def adopt_assistance(ticket_id: int, run_id: int, body: AdoptRequest, db: DbSession, user: CurrentUser):
    ticket = await lock_ticket(db, ticket_id)
    if ticket.status not in {"pending", "processing"}:
        raise HTTPException(409, "当前状态不能采用建议")
    run = await db.scalar(
        select(AssistanceRun).where(AssistanceRun.id == run_id, AssistanceRun.ticket_id == ticket_id).with_for_update()
    )
    if run is None:
        raise HTTPException(404, "建议记录不存在或不属于当前工单")
    if run.adopted_at is not None:
        raise HTTPException(409, "该建议已采用，请勿重复提交")
    if case_fingerprint(ticket) != run.ticket_fingerprint:
        raise HTTPException(409, "工单内容已变化，请重新生成建议")
    await check_sources(db, [SourceSnapshot.model_validate(source) for source in run.sources], lock=True)
    run.adopted_at = datetime.now(UTC)
    run.adopted_by = user.id
    run.final_solution = body.solution
    run.final_reply = body.reply
    add_record(
        ticket,
        user.id,
        "ai_adopted",
        f"人工确认采用AI建议 #{run.id}\n处理方案：{body.solution}\n回复草稿（未发送）：{body.reply}",
    )
    await db.commit()
    return run
