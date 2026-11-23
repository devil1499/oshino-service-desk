import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ai_settings import AiConfigurationError, load_chat_settings
from app.core.database import SessionFactoryDep
from app.core.security import CurrentUser, DbSession
from app.integrations.chat import ChatClient, ChatError
from app.models import BasicAnalysis, TicketCategory
from app.modules.tickets.service import add_record, get_ticket, lock_ticket, validate_catalog

router = APIRouter(prefix="/api/tickets", tags=["基础分析"])
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class BasicResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: Text
    category_id: int = Field(gt=0)
    priority: Literal["P1", "P2", "P3", "P4"]
    reason: Text


class AnalysisView(BaseModel):
    status: Literal["not_started", "pending", "running", "completed", "failed"]
    attempt: int
    result: BasicResult | None
    error: str | None
    model: str | None
    stale: bool
    adopted_at: datetime | None


class ConfirmAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: Literal[True]


def fingerprint(ticket):
    data = [ticket.title, ticket.description, ticket.product_id, ticket.module_id]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()


async def queue_analysis(db, ticket):
    row = (await db.get(BasicAnalysis, ticket.id))
    if row is not None and row.status in {"pending", "running"}:
        raise HTTPException(409, "分析正在进行，请等待完成")
    if row is None:
        row = BasicAnalysis(ticket_id=ticket.id, attempt=1)
        db.add(row)
    else:
        row.attempt += 1
    row.status = "pending"
    row.fingerprint = fingerprint(ticket)
    row.result = None
    row.error = None
    row.model = None
    row.prompt_version = "basic-v1"
    row.adopted_at = None
    row.updated_at = datetime.now(UTC)
    return row


async def interrupt_analyses(session_factory: async_sessionmaker[AsyncSession]):
    # 教程按单进程运行；进程重启后原后台任务已经不存在。
    async with session_factory.begin() as db:
        (await db.execute(
            update(BasicAnalysis)
            .where(BasicAnalysis.status.in_(["pending", "running"]))
            .values(status="failed", error="上次分析被服务重启中断，请手动重新分析")
        ))


async def run_analysis(session_factory: async_sessionmaker[AsyncSession], ticket_id: int, attempt: int):
    async with session_factory() as db:
        row = (await db.get(BasicAnalysis, ticket_id))
        if row is None:
            raise RuntimeError("基础分析任务记录不存在")
        if row.attempt != attempt or row.status != "pending":
            return
        ticket = await get_ticket(db, ticket_id)
        categories = [
            {"id": c.id, "name": c.name}
            for c in (await db.scalars(select(TicketCategory).where(TicketCategory.is_active))).all()
        ]
        data = {"title": ticket.title, "description": ticket.description, "categories": categories}
        row.status = "running"
        await db.commit()
    result = None
    model_name = None
    error_message = None
    try:
        config = await asyncio.to_thread(load_chat_settings)
        model_name = config.chat_model
        async with await asyncio.to_thread(ChatClient,
            str(config.chat_base_url), config.chat_api_key.get_secret_value(), config.chat_model
        ) as chat:
            result = (await asyncio.to_thread(chat.ask,
                "概括工单，从给出的启用分类中选择category_id，建议P1至P4优先级并解释原因。",
                data,
                BasicResult,
            ))
        if result.category_id not in {c["id"] for c in categories}:
            raise ChatError("模型返回了不属于启用分类的 ID")
    except ValidationError:
        error_message = "聊天模型配置缺失或无效，请检查 backend/.env.chat"
    except (ChatError, AiConfigurationError) as error:
        error_message = str(error)
    async with session_factory.begin() as db:
        row = (await db.get(BasicAnalysis, ticket_id))
        if row is None:
            raise RuntimeError("基础分析任务记录不存在")
        if row.attempt != attempt:
            return
        row.model = model_name
        row.updated_at = datetime.now(UTC)
        ticket = await get_ticket(db, ticket_id)
        if fingerprint(ticket) != row.fingerprint:
            error_message = "分析期间工单内容已变化，请重新分析"
        row.status = "failed" if error_message else "completed"
        row.error = error_message
        if error_message:
            row.result = None
        else:
            assert result is not None
            row.result = result.model_dump()


@router.get("/{ticket_id}/analysis", response_model=AnalysisView)
async def read_analysis(ticket_id: int, db: DbSession, user: CurrentUser):
    ticket = (await get_ticket(db, ticket_id))
    row = (await db.get(BasicAnalysis, ticket_id))
    if row is None:
        return AnalysisView(
            status="not_started", attempt=0, result=None, error=None, model=None, stale=False,
            adopted_at=None,
        )
    return AnalysisView.model_validate({
        "status": row.status,
        "attempt": row.attempt,
        "result": row.result,
        "error": row.error,
        "model": row.model,
        "stale": row.fingerprint != fingerprint(ticket),
        "adopted_at": row.adopted_at,
    })


@router.post("/{ticket_id}/analysis", status_code=202)
async def retry_analysis(
    ticket_id: int, db: DbSession, user: CurrentUser, background: BackgroundTasks,
    session_factory: SessionFactoryDep,
):
    ticket = (await lock_ticket(db, ticket_id))
    row = (await queue_analysis(db, ticket))
    await db.commit()
    background.add_task(run_analysis, session_factory, ticket_id, row.attempt)
    return {"status": "pending"}


@router.post("/{ticket_id}/analysis/adopt")
async def adopt_analysis(ticket_id: int, body: ConfirmAnalysis, db: DbSession, user: CurrentUser):
    ticket = (await lock_ticket(db, ticket_id))
    row = (await db.scalar(
        select(BasicAnalysis).where(BasicAnalysis.ticket_id == ticket_id).with_for_update()
    ))
    if row is None or row.status != "completed" or row.adopted_at is not None or row.fingerprint != fingerprint(ticket):
        raise HTTPException(409, "没有可采用的最新分析，请重新分析")
    result = BasicResult.model_validate(row.result)
    await validate_catalog(db, ticket.product_id, ticket.module_id, result.category_id)
    ticket.category_id = result.category_id
    ticket.priority = result.priority
    row.adopted_at = datetime.now(UTC)
    add_record(ticket, user.id, "analysis", "人工确认基础分析建议：更新分类与优先级")
    await db.commit()
    return {"status": "adopted"}
