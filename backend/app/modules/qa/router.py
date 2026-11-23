from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.core.database import SessionFactoryDep
from app.core.security import CurrentUser, DbSession
from app.integrations.chat import ChatClient
from app.models import QaConversation, QaMessage
from app.modules.analysis.assistance import EmbeddingModel, get_chat_client
from app.modules.analysis.router import RetrievalConfig
from app.modules.qa.schemas import (
    ConversationInput,
    ConversationPage,
    ConversationView,
    MessageInput,
    MessagePage,
    MessageView,
)
from app.modules.qa.service import create_conversation, owned_conversation, send_question

router = APIRouter(prefix="/api/qa/conversations", tags=["智能助手"])
ChatModel = Annotated[ChatClient, Depends(get_chat_client)]


@router.post("", response_model=ConversationView, status_code=201)
async def create(body: ConversationInput, db: DbSession, user: CurrentUser):
    return await create_conversation(db, user.id, body)


@router.get("", response_model=ConversationPage)
async def list_conversations(
    db: DbSession, user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
):
    total = await db.scalar(select(func.count()).select_from(QaConversation).where(
        QaConversation.owner_id == user.id, QaConversation.is_evaluation.is_(False)))
    items = (
        await db.scalars(
            select(QaConversation).where(QaConversation.owner_id == user.id, QaConversation.is_evaluation.is_(False))
            .order_by(QaConversation.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{conversation_id}/messages", response_model=MessagePage)
async def list_messages(
    conversation_id: int, db: DbSession, user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
):
    await owned_conversation(db, conversation_id, user.id)
    total = await db.scalar(
        select(func.count()).select_from(QaMessage).where(QaMessage.conversation_id == conversation_id)
    )
    items = (
        await db.scalars(
            select(QaMessage).where(QaMessage.conversation_id == conversation_id)
            .order_by(QaMessage.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return {"items": list(reversed(items)), "total": total, "page": page, "page_size": page_size}


@router.post("/{conversation_id}/messages", response_model=MessageView, status_code=201)
async def send(
    conversation_id: int, body: MessageInput, db: DbSession, user: CurrentUser,
    session_factory: SessionFactoryDep, config: RetrievalConfig, embedding: EmbeddingModel, chat: ChatModel,
):
    owner_id = user.id
    # 登录依赖读取用户后，先释放该会话占用的连接；模型调用由独立短事务围住。
    await db.rollback()
    return await send_question(session_factory, conversation_id, owner_id, body, config, embedding, chat)


@router.get('/{conversation_id}/messages/{message_id}/run')
async def run_details(conversation_id: int, message_id: int, db: DbSession, user: CurrentUser):
    await owned_conversation(db, conversation_id, user.id)
    message = await db.scalar(select(QaMessage).where(
        QaMessage.id == message_id, QaMessage.conversation_id == conversation_id, QaMessage.role == 'assistant'))
    if message is None or message.run_details is None:
        raise HTTPException(404, '本条回答没有运行记录；旧回答不会补造数据')
    return message.run_details
