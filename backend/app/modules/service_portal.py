"""客户售后会话与客服接单；所有身份和归属在服务端核对。"""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select

from app.core.database import SessionFactoryDep
from app.core.security import AuthenticatedUser, CurrentUser, DbSession
from app.models import Product, ProductModule, QaConversation, QaMessage, Ticket, TicketCategory, User
from app.modules.analysis.assistance import get_chat_client
from app.modules.analysis.router import get_embedding_client, get_retrieval_settings
from app.modules.qa.schemas import ConversationInput, MessageInput
from app.modules.qa.service import create_conversation, owned_conversation, send_question
from app.modules.tickets.service import add_record

router = APIRouter(prefix="/api/service", tags=["客户服务"])
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


def require_customer(user: AuthenticatedUser):
    if user.role != "customer":
        raise HTTPException(403, "此入口仅供客户使用")
    return user


Customer = Annotated[User, Depends(require_customer)]


class Handoff(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: Text
    priority: Literal["P1", "P2", "P3", "P4"]


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: Text


class Transfer(Reply):
    level: int = Field(ge=1, le=3)


class Triage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    priority: Literal["P1", "P2", "P3", "P4"]


async def service_product(db, product_id):
    module = await db.scalar(
        select(ProductModule)
        .join(Product)
        .where(
            Product.id == product_id,
            Product.is_active,
            ProductModule.is_active,
            ProductModule.name == "售后服务",
        )
    )
    if module is None:
        raise HTTPException(422, "该产品尚未开放客户售后服务")
    return module


async def conversation_for(db, conversation_id, user, *, lock=False):
    query = select(QaConversation).where(QaConversation.id == conversation_id)
    if user.role == "customer":
        query = query.where(QaConversation.owner_id == user.id)
    else:
        query = query.join(User, User.id == QaConversation.owner_id).where(
            User.role == "customer", QaConversation.ticket_id.is_not(None)
        )
    row = await db.scalar(query.with_for_update(of=QaConversation) if lock else query)
    if row is None:
        raise HTTPException(404, "服务会话不存在")
    return row


async def ticket_for(db, conversation):
    if conversation.ticket_id is None:
        raise HTTPException(409, "该会话尚未转人工")
    return await db.scalar(select(Ticket).where(Ticket.id == conversation.ticket_id).with_for_update())


def assigned(ticket, user):
    if ticket.owner_id != user.id and user.role != "admin":
        raise HTTPException(403, "只有当前接单客服或管理员可以处理")


async def card(db, conversation):
    customer = await db.get(User, conversation.owner_id)
    product = await db.get(Product, conversation.product_id)
    ticket = await db.get(Ticket, conversation.ticket_id) if conversation.ticket_id else None
    staff = await db.get(User, ticket.owner_id) if ticket and ticket.owner_id else None
    return dict(
        id=conversation.id,
        title=conversation.title,
        product_name=product.name,
        customer_name=customer.display_name,
        customer_tier=customer.customer_tier,
        ticket_id=ticket.id if ticket else None,
        priority=ticket.priority if ticket else None,
        status=ticket.status if ticket else "ai",
        owner_id=ticket.owner_id if ticket else None,
        owner_name=staff.display_name if staff else None,
        staff_level=staff.staff_level if staff else None,
        required_level=ticket.required_level if ticket else 1,
        created_at=ticket.created_at if ticket else conversation.created_at,
        solution=ticket.solution if ticket else "",
    )


@router.get("/products")
async def products(db: DbSession, user: Customer):
    rows = (
        await db.scalars(
            select(Product)
            .join(ProductModule)
            .where(
                Product.is_active,
                ProductModule.is_active,
                ProductModule.name == "售后服务",
            )
            .order_by(Product.id)
        )
    ).all()
    return [dict(id=p.id, name=p.name) for p in rows]


@router.get("/people")
async def people(db: DbSession, user: CurrentUser, page: Annotated[int, Query(ge=1)] = 1):
    rows = (
        await db.scalars(
            select(User).where(User.is_active).order_by(User.role, User.id).offset((page - 1) * 50).limit(51)
        )
    ).all()
    return dict(
        items=[
            dict(id=p.id, name=p.display_name, role=p.role, tier=p.customer_tier, level=p.staff_level)
            for p in rows[:50]
        ],
        has_more=len(rows) > 50,
    )


@router.post("/conversations", status_code=201)
async def create(body: ConversationInput, db: DbSession, user: Customer):
    await service_product(db, body.product_id)
    row = await create_conversation(db, user.id, body)
    return await card(db, row)


@router.get("/conversations")
async def conversations(db: DbSession, user: AuthenticatedUser, page: Annotated[int, Query(ge=1)] = 1):
    query = (
        select(QaConversation)
        .join(User, User.id == QaConversation.owner_id)
        .outerjoin(
            Ticket,
            Ticket.id == QaConversation.ticket_id,
        )
        .where(User.role == "customer")
    )
    if user.role == "customer":
        query = query.where(QaConversation.owner_id == user.id).order_by(QaConversation.id.desc())
    else:
        query = query.where(QaConversation.ticket_id.is_not(None)).order_by(
            Ticket.priority,
            User.customer_tier.desc(),
            Ticket.created_at,
            Ticket.id,
        )
    rows = (await db.scalars(query.offset((page - 1) * 50).limit(51))).all()
    return dict(items=[await card(db, row) for row in rows[:50]], has_more=len(rows) > 50)


@router.get("/conversations/{conversation_id}")
async def detail(
    conversation_id: int, db: DbSession, user: AuthenticatedUser, before: Annotated[int | None, Query(gt=0)] = None
):
    row = await conversation_for(db, conversation_id, user)
    query = select(QaMessage).where(QaMessage.conversation_id == row.id)
    if before is not None:
        query = query.where(QaMessage.id < before)
    messages = (await db.scalars(query.order_by(QaMessage.id.desc()).limit(101))).all()
    result = await card(db, row)
    result["messages"] = [
        dict(id=m.id, role=m.role, content=m.content, status=m.status, sources=m.sources, created_at=m.created_at)
        for m in reversed(messages[:100])
    ]
    result["has_older"] = len(messages) > 100
    # 内部工单备注不在客户对话中公开，仅展示明确面向双方的服务记录。
    ticket = await db.get(Ticket, row.ticket_id) if row.ticket_id else None
    result["records"] = (
        [
            dict(id=r.id, content=r.content, kind=r.kind, created_at=r.created_at)
            for r in ticket.records
            if r.kind.startswith("service_")
        ]
        if ticket
        else []
    )
    return result


class CustomerMessageInput(MessageInput):
    # 本次联网功能仅面向客服端，客户入口不接受开启联网的请求。
    web_search: Literal[False] = False


@router.post("/conversations/{conversation_id}/ai")
async def ai(conversation_id: int, body: CustomerMessageInput, db: DbSession, user: Customer, factory: SessionFactoryDep):
    await owned_conversation(db, conversation_id, user.id)
    owner_id = user.id
    await db.rollback()
    config = get_retrieval_settings()
    chat_generator = get_chat_client()
    embedding_generator = get_embedding_client(config)
    try:
        chat = next(chat_generator)
        embedding = next(embedding_generator)
        return await send_question(factory, conversation_id, owner_id, body, config, embedding, chat, record_run=False)
    finally:
        embedding_generator.close()
        chat_generator.close()


@router.post("/conversations/{conversation_id}/handoff")
async def handoff(conversation_id: int, body: Handoff, db: DbSession, user: Customer):
    row = await conversation_for(db, conversation_id, user, lock=True)
    if row.ticket_id:
        return await card(db, row)
    running = await db.scalar(
        select(QaMessage.id).where(
            QaMessage.conversation_id == row.id,
            QaMessage.status == "running",
        )
    )
    if running:
        raise HTTPException(409, "请等待当前智能回复结束后转人工")
    module = await service_product(db, row.product_id)
    category = await db.scalar(
        select(TicketCategory).where(
            TicketCategory.name == "待人工分类",
            TicketCategory.is_active,
        )
    )
    if category is None:
        raise HTTPException(503, "缺少售后受理分类，请联系管理员")
    ticket = Ticket(
        title=row.title,
        description=body.description,
        customer_id=user.id,
        customer_name=user.display_name,
        customer_email="",
        product_id=row.product_id,
        module_id=module.id,
        category_id=category.id,
        priority=body.priority,
        owner_id=None,
        status="pending",
        solution="",
        records=[],
        required_level=1,
    )
    add_record(ticket, user.id, "service_transfer", "客户转人工：" + body.description)
    db.add(ticket)
    await db.flush()
    row.ticket_id = ticket.id
    await db.commit()
    return await card(db, row)


@router.post("/conversations/{conversation_id}/claim")
async def claim(conversation_id: int, db: DbSession, user: CurrentUser):
    row = await conversation_for(db, conversation_id, user, lock=True)
    ticket = await ticket_for(db, row)
    if ticket.status != "pending" or ticket.owner_id is not None:
        raise HTTPException(409, "该工单已被接走或不在待接状态")
    if user.role != "admin" and user.staff_level < ticket.required_level:
        raise HTTPException(403, "此工单需要更高级别客服")
    if ticket.previous_owner_id == user.id:
        raise HTTPException(409, "客户申请更换客服，请由其他客服接单")
    ticket.owner_id = user.id
    ticket.status = "processing"
    add_record(ticket, user.id, "service_transfer", f"{user.display_name} · L{user.staff_level} 已接入")
    await db.commit()
    return await card(db, row)


@router.post("/conversations/{conversation_id}/reply")
async def reply(conversation_id: int, body: Reply, db: DbSession, user: AuthenticatedUser):
    row = await conversation_for(db, conversation_id, user, lock=True)
    ticket = await ticket_for(db, row)
    if ticket.status == "closed":
        raise HTTPException(409, "会话已结束，请新建咨询")
    if user.role != "customer":
        assigned(ticket, user)
        if ticket.status != "processing":
            raise HTTPException(409, "请先接单再回复")
    name = user.display_name if user.role == "customer" else f"{user.display_name} · L{user.staff_level}"
    add_record(
        ticket, user.id, "service_customer" if user.role == "customer" else "service_reply", name + "：" + body.text
    )
    await db.commit()
    return {"status": "sent"}


@router.post("/conversations/{conversation_id}/transfer")
async def transfer(conversation_id: int, body: Transfer, db: DbSession, user: AuthenticatedUser):
    row = await conversation_for(db, conversation_id, user, lock=True)
    ticket = await ticket_for(db, row)
    if ticket.status not in {"processing", "resolved"} or ticket.owner_id is None:
        raise HTTPException(409, "只有已接单且未关闭的工单可以转交")
    if user.role != "customer":
        assigned(ticket, user)
        ticket.required_level = body.level
    elif body.level != ticket.required_level:
        raise HTTPException(422, "客户不能更改客服处理等级")
    ticket.previous_owner_id = ticket.owner_id
    ticket.owner_id = None
    ticket.status = "pending"
    ticket.resolved_at = None
    ticket.solution = ""
    add_record(ticket, user.id, "service_transfer", f"{user.display_name}申请转交：{body.text}")
    await db.commit()
    return await card(db, row)


@router.post("/conversations/{conversation_id}/priority")
async def triage(conversation_id: int, body: Triage, db: DbSession, user: CurrentUser):
    row = await conversation_for(db, conversation_id, user, lock=True)
    ticket = await ticket_for(db, row)
    assigned(ticket, user)
    if ticket.status != "processing":
        raise HTTPException(409, "只能调整处理中的工单")
    ticket.priority = body.priority
    add_record(ticket, user.id, "service_status", f"客服核定问题严重程度为 {body.priority}")
    await db.commit()
    return await card(db, row)


@router.post("/conversations/{conversation_id}/resolve")
async def resolve(conversation_id: int, body: Reply, db: DbSession, user: CurrentUser):
    row = await conversation_for(db, conversation_id, user, lock=True)
    ticket = await ticket_for(db, row)
    assigned(ticket, user)
    if ticket.status != "processing":
        raise HTTPException(409, "只能提交处理中的工单结果")
    ticket.status = "resolved"
    ticket.solution = body.text
    ticket.resolved_at = datetime.now(UTC)
    add_record(ticket, user.id, "service_status", "处理结果：" + body.text)
    await db.commit()
    return await card(db, row)


@router.post("/conversations/{conversation_id}/confirm")
async def confirm(conversation_id: int, db: DbSession, user: Customer):
    row = await conversation_for(db, conversation_id, user, lock=True)
    ticket = await ticket_for(db, row)
    if ticket.status != "resolved":
        raise HTTPException(409, "客服提交处理结果后才能确认")
    ticket.status = "closed"
    add_record(ticket, user.id, "service_status", "客户确认问题已解决")
    await db.commit()
    return await card(db, row)
