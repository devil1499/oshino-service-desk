from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from sqlalchemy import func, or_, select

from app.core.database import SessionFactoryDep
from app.core.security import CurrentUser, DbSession
from app.models import Ticket, User
from app.modules.analysis.basic import queue_analysis, run_analysis
from app.modules.tickets.schemas import (
    CloseRequest,
    NoteRequest,
    Priority,
    ResolveRequest,
    TicketCreate,
    TicketDetail,
    TicketPage,
    TicketPatch,
    TicketStatus,
)
from app.modules.tickets.service import (
    add_record,
    get_ticket,
    lock_ticket,
    validate_catalog,
    validate_owner,
)

router = APIRouter(prefix="/api/tickets", tags=["工单"])


@router.post("", response_model=TicketDetail, status_code=201)
async def create_ticket(
    body: TicketCreate, db: DbSession, user: CurrentUser,
    background: BackgroundTasks, session_factory: SessionFactoryDep,
):
    await validate_catalog(db, body.product_id, body.module_id, body.category_id)
    # model_dump 把校验后的请求转成字典，** 将字段作为参数交给 Ticket。
    ticket = Ticket(**body.model_dump(), owner_id=user.id)
    add_record(ticket, user.id, "created", "创建工单，状态为待处理")
    db.add(ticket)
    await db.flush()
    analysis = await queue_analysis(db, ticket)
    # 工单、处理记录和分析任务一起提交，后台才能读取到完整快照。
    await db.commit()
    background.add_task(run_analysis, session_factory, ticket.id, analysis.attempt)
    return ticket


@router.get("", response_model=TicketPage)
async def list_tickets(
    db: DbSession,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    keyword: Annotated[str | None, Query(max_length=200)] = None,
    status: TicketStatus | None = None,
    priority: Priority | None = None,
    product_id: Annotated[int | None, Query(gt=0)] = None,
    module_id: Annotated[int | None, Query(gt=0)] = None,
    category_id: Annotated[int | None, Query(gt=0)] = None,
    owner_id: Annotated[int | None, Query(gt=0)] = None,
    imported_only: bool = False,
):
    filters = []
    if imported_only:
        filters.append(Ticket.import_key.is_not(None))
    if keyword:
        filters.append(or_(Ticket.title.ilike(f"%{keyword}%"), Ticket.description.ilike(f"%{keyword}%")))
    for column, value in [
        (Ticket.status, status),
        (Ticket.priority, priority),
        (Ticket.product_id, product_id),
        (Ticket.module_id, module_id),
        (Ticket.category_id, category_id),
        (Ticket.owner_id, owner_id),
    ]:
        if value is not None:
            filters.append(column == value)
    total = await db.scalar(select(func.count()).select_from(Ticket).where(*filters))
    # 历史导入用于核对最近上传结果，工作队列则按业务优先级排队。
    order = (
        (Ticket.id.desc(),) if imported_only
        else (Ticket.priority, User.customer_tier.desc().nulls_last(), Ticket.created_at, Ticket.id)
    )
    # 查询条件与总数保持一致；offset 跳过前面各页，limit 限制本页条数。
    query = (
        select(Ticket)
        .outerjoin(User, User.id == Ticket.customer_id)
        .where(*filters)
        .order_by(*order)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.scalars(query)
    items = result.all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{ticket_id}", response_model=TicketDetail)
async def ticket_detail(ticket_id: int, db: DbSession, user: CurrentUser):
    return await get_ticket(db, ticket_id)


@router.patch("/{ticket_id}", response_model=TicketDetail)
async def update_ticket(ticket_id: int, body: TicketPatch, db: DbSession, user: CurrentUser):
    ticket = await lock_ticket(db, ticket_id)
    # PATCH 只修改请求里实际出现的字段，省略的字段保留原值。
    changes = body.model_dump(exclude_unset=True)
    await validate_catalog(
        db,
        changes.get("product_id", ticket.product_id),
        changes.get("module_id", ticket.module_id),
        changes.get("category_id", ticket.category_id),
        current=ticket,
    )
    if "owner_id" in changes and changes["owner_id"] != ticket.owner_id:
        await validate_owner(db, changes["owner_id"])
    for field, value in changes.items():
        setattr(ticket, field, value)
    add_record(ticket, user.id, "updated", "更新了工单信息")
    await db.commit()
    return ticket


@router.post("/{ticket_id}/records", response_model=TicketDetail, status_code=201)
async def write_note(ticket_id: int, body: NoteRequest, db: DbSession, user: CurrentUser):
    ticket = await lock_ticket(db, ticket_id)
    add_record(ticket, user.id, "note", body.content)
    await db.commit()
    return ticket


@router.post("/{ticket_id}/start", response_model=TicketDetail)
async def start_ticket(ticket_id: int, db: DbSession, user: CurrentUser):
    ticket = await lock_ticket(db, ticket_id)
    if ticket.status != "pending":
        raise HTTPException(status_code=409, detail="只有待处理工单可以开始处理")
    ticket.status = "processing"
    add_record(ticket, user.id, "status", "开始处理：待处理 → 处理中")
    await db.commit()
    return ticket


@router.post("/{ticket_id}/resolve", response_model=TicketDetail)
async def resolve_ticket(ticket_id: int, body: ResolveRequest, db: DbSession, user: CurrentUser):
    ticket = await lock_ticket(db, ticket_id)
    if ticket.status != "processing":
        raise HTTPException(status_code=409, detail="只有处理中工单可以标记已解决")
    ticket.solution = body.solution
    ticket.status = "resolved"
    ticket.resolved_at = datetime.now(UTC)
    add_record(ticket, user.id, "status", "保存解决方案：处理中 → 已解决")
    await db.commit()
    return ticket


@router.post("/{ticket_id}/close", response_model=TicketDetail)
async def close_ticket(ticket_id: int, body: CloseRequest, db: DbSession, user: CurrentUser):
    ticket = await lock_ticket(db, ticket_id)
    if ticket.status != "resolved":
        raise HTTPException(status_code=409, detail="只有已解决工单可以关闭")
    ticket.status = "closed"
    add_record(ticket, user.id, "status", "客服确认已完成客户回复：已解决 → 已关闭")
    await db.commit()
    return ticket
