import asyncio
import logging
import time

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ai_settings import AiConfigurationError, get_ai_store
from app.core.retrieval_settings import RetrievalSettings
from app.integrations.chat import ChatClient, ChatError
from app.integrations.embeddings import EmbeddingClient, EmbeddingError
from app.integrations.hybrid_index import IndexNotReady
from app.integrations.web_search import WebSearchError, WebSource
from app.models import KnowledgeChunk, KnowledgeDocument, Product, QaConversation, QaMessage
from app.modules.knowledge.text import document_fingerprint
from app.modules.qa.adapters import model_adapter, search_adapter, web_search_adapter
from app.modules.qa.graph import Answer, InvalidCitation, Message, Question, Source, ask, build_graph
from app.modules.qa.schemas import ConversationInput, MessageInput, MessageView
from app.modules.qa.trace import RunTrace, usage_summary

logger = logging.getLogger(__name__)
PROMPT_VERSION = "qa-v2-compact"
QUESTION_TIMEOUT_SECONDS = 150


async def owned_conversation(db: AsyncSession, conversation_id: int, owner_id: int, *, lock: bool = False):
    query = select(QaConversation).where(QaConversation.id == conversation_id, QaConversation.owner_id == owner_id)
    conversation = await db.scalar(query.with_for_update() if lock else query)
    if conversation is None:
        raise HTTPException(404, "问答会话不存在")
    return conversation


async def create_conversation(db: AsyncSession, owner_id: int, body: ConversationInput) -> QaConversation:
    product = await db.get(Product, body.product_id)
    if product is None or not product.is_active:
        raise HTTPException(422, "请选择有效产品")
    conversation = QaConversation(owner_id=owner_id, product_id=body.product_id, title=body.title)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def recent_history(db: AsyncSession, conversation_id: int) -> list[Message]:
    rows = (
        await db.scalars(
            select(QaMessage)
            .where(QaMessage.conversation_id == conversation_id)
            .order_by(QaMessage.id.desc())
            .limit(36)
        )
    ).all()
    ordered = list(reversed(rows))
    users = {row.request_id: row for row in ordered if row.role == "user"}
    pairs = []
    for assistant in ordered:
        if assistant.role != "assistant" or assistant.status not in {"answered", "clarification", "insufficient"}:
            continue
        user = users.get(assistant.request_id)
        if user is not None:
            pairs.append(
                (
                    Message(role="user", content=user.content),
                    Message(role="assistant", content=assistant.content),
                )
            )
    selected = []
    used_chars = 0
    for pair in reversed(pairs):
        size = sum(len(message.content) for message in pair)
        if len(selected) == 6 or used_chars + size > 6000:
            break
        selected.append(pair)
        used_chars += size
    return [message for pair in reversed(selected) for message in pair]


async def prepare_question(
    session_factory: async_sessionmaker[AsyncSession], conversation_id: int, owner_id: int, body: MessageInput
) -> tuple[QaMessage, Question | None]:
    request_id = str(body.request_id)
    async with session_factory.begin() as db:
        conversation = await owned_conversation(db, conversation_id, owner_id, lock=True)
        if conversation.ticket_id is not None:
            raise HTTPException(409, "已转人工，请在服务会话中继续沟通")
        previous = await db.scalar(
            select(QaMessage).where(
                QaMessage.conversation_id == conversation_id,
                QaMessage.request_id == request_id,
                QaMessage.role == "user",
            )
        )
        if previous is not None:
            if previous.content != body.text or previous.web_search != body.web_search:
                raise HTTPException(409, "同一请求编号不能用于不同问题")
            assistant = await db.scalar(
                select(QaMessage).where(
                    QaMessage.conversation_id == conversation_id,
                    QaMessage.request_id == request_id,
                    QaMessage.role == "assistant",
                )
            )
            if assistant is None:
                raise RuntimeError("问答消息记录不完整")
            return assistant, None
        product = await db.get(Product, conversation.product_id)
        if product is None or not product.is_active:
            raise HTTPException(409, "会话产品已停用，请选择有效产品新建会话")
        running = await db.scalar(
            select(QaMessage.id).where(
                QaMessage.conversation_id == conversation_id,
                QaMessage.role == "assistant",
                QaMessage.status == "running",
            )
        )
        if running is not None:
            raise HTTPException(409, "该会话正在回答，请等待本轮结束")
        history = await recent_history(db, conversation_id)
        db.add(
            QaMessage(
                conversation_id=conversation_id,
                request_id=request_id,
                role="user",
                content=body.text,
                status="submitted",
                sources=[],
                web_search=body.web_search,
            )
        )
        assistant = QaMessage(
            conversation_id=conversation_id,
            request_id=request_id,
            role="assistant",
            content="",
            status="running",
            sources=[],
            web_search=body.web_search,
        )
        db.add(assistant)
        await db.flush()
        question = Question(text=body.text, product_id=conversation.product_id, history=history, web_search=body.web_search)
    return assistant, question


async def verify_sources(db: AsyncSession, product_id: int, sources: list[Source | WebSource]) -> None:
    for source in sorted((s for s in sources if isinstance(s, Source)), key=lambda item: item.document_id):
        document = await db.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.id == source.document_id).with_for_update()
        )
        chunk = await db.get(KnowledgeChunk, source.chunk_id)
        if (
            document is None
            or chunk is None
            or document.status != "published"
            or document.product_id != product_id
            or chunk.document_id != source.document_id
            or document_fingerprint(document) != source.fingerprint
            or chunk.fingerprint != source.fingerprint
        ):
            raise HTTPException(409, "引用资料已变化或停用，请重建索引后重新提问")


async def finish_question(
    session_factory: async_sessionmaker[AsyncSession],
    message_id: int,
    product_id: int,
    answer: Answer,
    model: str,
    duration_ms: int,
    trace: RunTrace | None = None,
) -> MessageView:
    async with session_factory.begin() as db:
        if trace is None:
            await verify_sources(db, product_id, answer.sources)
        else:

            async def verify(data):
                await verify_sources(db, product_id, answer.sources)
                return {"verified_sources": len(answer.sources)}

            # 核验持有文档锁，记录随最终回答一起提交，不能在事务内再借一条连接。
            await trace.run_step("verify_sources", verify, {"sources": answer.sources}, checkpoint=False)
        message = await db.scalar(select(QaMessage).where(QaMessage.id == message_id).with_for_update())
        if message is None or message.status != "running":
            raise HTTPException(409, "本轮问答已中断，请重新提问")
        message.content = answer.text
        message.status = answer.status
        message.sources = [source.model_dump(mode='json') for source in answer.sources]
        message.model = model
        message.prompt_version = PROMPT_VERSION
        message.duration_ms = duration_ms
        if trace is not None:
            trace.finish(answer.status, sources=answer.sources)
            message.run_details = trace.snapshot()
            message.duration_ms = message.run_details["duration_ms"]
        result = MessageView.model_validate(message)
    return result


async def fail_question(
    session_factory: async_sessionmaker[AsyncSession],
    message_id: int,
    status_code: int,
    message: str,
    duration_ms: int,
    trace: RunTrace | None = None,
) -> None:
    values = dict(status="failed", content=message, error_code=f"HTTP_{status_code}", duration_ms=duration_ms)
    if trace is not None:
        trace.finish("failed", error=message)
        values.update(run_details=trace.snapshot(), model=trace.data["model"], prompt_version=PROMPT_VERSION)
    async with session_factory.begin() as db:
        await db.execute(
            update(QaMessage).where(QaMessage.id == message_id, QaMessage.status == "running").values(**values)
        )


async def interrupt_questions(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory.begin() as db:
        rows = (
            await db.scalars(
                select(QaMessage).where(QaMessage.role == "assistant", QaMessage.status == "running").with_for_update()
            )
        ).all()
        for message in rows:
            message.status = "failed"
            message.content = "服务重启中断了本轮回答，请重新提问"
            message.error_code = "INTERRUPTED"
            message.duration_ms = None
            if message.run_details is not None:
                details = dict(message.run_details)
                details.update(status="failed", error=message.content, duration_ms=None, interrupted=True)
                for entry in details["steps"] + details["calls"]:
                    if entry["status"] == "running":
                        entry.update(status="failed", error="INTERRUPTED", duration_ms=None)
                details["usage"] = {
                    kind: {**usage_summary(details["calls"], kind), "complete": False} for kind in ("chat", "embedding")
                }
                message.run_details = details


async def send_question(
    session_factory: async_sessionmaker[AsyncSession],
    conversation_id: int,
    owner_id: int,
    body: MessageInput,
    config: RetrievalSettings,
    embedding: EmbeddingClient,
    chat: ChatClient,
    *,
    record_run: bool = True,
) -> MessageView:
    started = time.monotonic()
    message, question = await prepare_question(session_factory, conversation_id, owner_id, body)
    if question is None:
        return MessageView.model_validate(message)

    async def checkpoint(details):
        async with session_factory.begin() as db:
            await db.execute(
                update(QaMessage)
                .where(QaMessage.id == message.id, QaMessage.status == "running")
                .values(run_details=details, model=chat.model, prompt_version=PROMPT_VERSION)
            )

    trace = RunTrace(chat.model, PROMPT_VERSION, question.model_dump(), checkpoint) if record_run else None
    if trace is not None:
        trace.started = started
    try:
        if question.web_search:
            await asyncio.to_thread(get_ai_store().search_key)
        graph = build_graph(
            model_adapter(chat, trace), search_adapter(config, embedding, session_factory, trace), trace,
            web_search=web_search_adapter(trace),
        )
        async with asyncio.timeout(QUESTION_TIMEOUT_SECONDS):
            answer = await ask(graph, question)
        return await finish_question(
            session_factory,
            message.id,
            question.product_id,
            answer,
            chat.model,
            round((time.monotonic() - started) * 1000),
            trace,
        )
    except (Exception, asyncio.CancelledError) as error:
        if isinstance(error, HTTPException):
            failure = error
        elif isinstance(error, IndexNotReady):
            failure = HTTPException(503, str(error))
        elif isinstance(error, AiConfigurationError):
            failure = HTTPException(503, str(error))
        elif isinstance(error, (ChatError, EmbeddingError, InvalidCitation, WebSearchError)):
            failure = HTTPException(502, str(error))
        elif isinstance(error, TimeoutError):
            failure = HTTPException(504, "问答超过150秒，请重新提问")
        elif isinstance(error, asyncio.CancelledError):
            failure = HTTPException(503, "请求中断，请重新提问")
        else:
            logger.error("问答失败，message_id=%s，error_type=%s", message.id, type(error).__name__)
            failure = HTTPException(500, "服务器处理问答失败，请联系管理员")
        try:
            await asyncio.shield(
                fail_question(
                    session_factory,
                    message.id,
                    failure.status_code,
                    failure.detail,
                    round((time.monotonic() - started) * 1000),
                    trace,
                )
            )
        except Exception:
            logger.exception("更新问答失败状态时数据库不可用，message_id=%s", message.id)
        if isinstance(error, asyncio.CancelledError):
            raise
        raise failure from error
