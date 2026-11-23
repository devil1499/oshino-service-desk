import asyncio
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import CurrentUser, DbSession
from app.integrations import smtp
from app.models import AssistanceRun, EmailDelivery
from app.modules.tickets.service import get_ticket, lock_ticket

router = APIRouter(prefix="/api/tickets", tags=["客户邮件"])
Subject = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Content = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]


class SendEmail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    recipient: EmailStr
    subject: Subject
    content: Content
    confirmed: Literal[True]
    assistance_id: int | None = Field(default=None, gt=0)

    @field_validator("subject")
    @classmethod
    def single_line(cls, value):
        if "\r" in value or "\n" in value:
            raise ValueError("邮件主题不能包含换行")
        return value


class EmailView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    request_id: str
    recipient: str
    subject: str
    content: str
    assistance_id: int | None
    message_id: str
    status: Literal["sending", "accepted", "failed", "unknown"]
    error: str | None
    created_at: datetime
    finished_at: datetime | None


async def interrupt_deliveries(session_factory: async_sessionmaker[AsyncSession]):
    async with session_factory.begin() as db:
        (await db.execute(
            update(EmailDelivery)
            .where(EmailDelivery.status == "sending")
            .values(
                status="unknown", error="服务在发送期间重启，结果无法确认；请核查邮箱和服务端记录"
            )
        ))


async def existing_request(db, body, ticket_id):
    row = (await db.scalar(select(EmailDelivery).where(EmailDelivery.request_id == str(body.request_id))))
    if row is None:
        return None
    if (row.ticket_id, row.recipient, row.subject, row.content, row.assistance_id) != (
        ticket_id,
        str(body.recipient),
        body.subject,
        body.content,
        body.assistance_id,
    ):
        raise HTTPException(409, "同一发送请求号不能用于不同内容或工单")
    return row


@router.get("/{ticket_id}/emails", response_model=list[EmailView])
async def list_emails(
    ticket_id: int, db: DbSession, user: CurrentUser, page: Annotated[int, Query(ge=1)] = 1
):
    await get_ticket(db, ticket_id)
    return (await db.scalars(
        select(EmailDelivery)
        .where(EmailDelivery.ticket_id == ticket_id)
        .order_by(EmailDelivery.id.desc())
        .offset((page - 1) * 10)
        .limit(10)
    )).all()


@router.post("/{ticket_id}/emails", response_model=EmailView, status_code=201)
async def send_email(ticket_id: int, body: SendEmail, db: DbSession, user: CurrentUser):
    existing = (await existing_request(db, body, ticket_id))
    if existing is not None:
        return existing
    await lock_ticket(db, ticket_id)
    # 同一工单的并发提交在锁后再次检查，防止同一 UUID 被同时投递。
    existing = (await existing_request(db, body, ticket_id))
    if existing is not None:
        return existing
    try:
        config = smtp.SmtpSettings.model_validate({})
    except ValidationError as error:
        raise HTTPException(503, "SMTP 配置缺失或无效，请检查 backend/.env.smtp") from error
    if not config.allowed(str(body.recipient)):
        raise HTTPException(422, "当前学习版本只允许发送到 SMTP_TEST_RECIPIENTS 中的测试邮箱")
    if body.assistance_id is not None:
        run = (await db.get(AssistanceRun, body.assistance_id))
        if run is None or run.ticket_id != ticket_id:
            raise HTTPException(422, "回复建议不属于当前工单")
    row = EmailDelivery(
        request_id=str(body.request_id),
        ticket_id=ticket_id,
        author_id=user.id,
        assistance_id=body.assistance_id,
        recipient=str(body.recipient),
        subject=body.subject,
        content=body.content,
        message_id=f"<{body.request_id}@{str(config.smtp_from).split('@')[1]}>",
        status="sending",
    )
    db.add(row)
    await db.commit()
    # 先持久化人工确认的内容，再进行不可回滚的外部投递。
    try:
        (await asyncio.to_thread(smtp.deliver,
            config,
            {
                "recipient": row.recipient,
                "subject": row.subject,
                "content": row.content,
                "message_id": row.message_id,
            },
        ))
        row.status = "accepted"
    except smtp.DeliveryRejected as error:
        row.status = "failed"
        row.error = str(error)
    except smtp.DeliveryUnknown as error:
        row.status = "unknown"
        row.error = str(error)
    row.finished_at = datetime.now(UTC)
    await db.commit()
    return row
