from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product, ProductModule, Ticket, TicketCategory, TicketRecord, User


async def get_ticket(db: AsyncSession, ticket_id: int) -> Ticket:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="工单不存在")
    return ticket


async def lock_ticket(db: AsyncSession, ticket_id: int) -> Ticket:
    # 同一工单的写操作排队执行，避免两名客服同时推进状态。
    ticket = await db.scalar(select(Ticket).where(Ticket.id == ticket_id).with_for_update())
    if ticket is None:
        raise HTTPException(status_code=404, detail="工单不存在")
    if ticket.status == "closed":
        raise HTTPException(status_code=409, detail="已关闭工单只允许查看")
    if ticket.customer_id is not None:
        raise HTTPException(status_code=409, detail="客户服务工单请在服务工作台处理")
    return ticket


async def validate_catalog(
    db: AsyncSession,
    product_id: int,
    module_id: int,
    category_id: int,
    current: Ticket | None = None,
) -> None:
    product = await db.get(Product, product_id)
    module = await db.get(ProductModule, module_id)
    category = await db.get(TicketCategory, category_id)
    if product is None or module is None or category is None:
        raise HTTPException(status_code=422, detail="产品、模块或分类不存在")
    if module.product_id != product.id:
        raise HTTPException(status_code=422, detail="模块不属于所选产品")
    # 旧工单可以保留已停用的配置，但新选择必须处于启用状态。
    for field, item in [("product_id", product), ("module_id", module), ("category_id", category)]:
        unchanged = current is not None and getattr(current, field) == item.id
        if not unchanged and not item.is_active:
            raise HTTPException(status_code=422, detail="新工单或新选择必须使用启用的配置")


async def validate_owner(db: AsyncSession, owner_id: int) -> None:
    owner = await db.get(User, owner_id)
    if owner is None or not owner.is_active or owner.role not in {"admin", "staff"}:
        raise HTTPException(status_code=422, detail="负责人必须是启用的用户")


def add_record(ticket: Ticket, author_id: int, kind: str, content: str) -> None:
    ticket.updated_at = datetime.now(UTC)
    ticket.records.append(TicketRecord(author_id=author_id, kind=kind, content=content))
