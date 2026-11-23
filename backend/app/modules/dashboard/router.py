from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import extract, func, select

from app.core.security import CurrentUser, DbSession
from app.models import Ticket

router = APIRouter(prefix="/api/dashboard", tags=["统计看板"])


class DashboardView(BaseModel):
    total: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    resolution_samples: int
    average_resolution_hours: float | None


@router.get("", response_model=DashboardView)
async def dashboard(db: DbSession, user: CurrentUser, product_id: Annotated[int | None, Query(gt=0)] = None):
    filters = [] if product_id is None else [Ticket.product_id == product_id]
    # 同一条聚合查询返回所有指标，避免并发修改时各卡片使用不同数据快照。
    statuses = ["pending", "processing", "resolved", "closed"]
    priorities = ["P1", "P2", "P3", "P4"]
    resolved = Ticket.status.in_(["resolved", "closed"]) & Ticket.resolved_at.is_not(None)
    columns = [func.count().label("total")]
    columns += [func.count().filter(Ticket.status == key).label(key) for key in statuses]
    columns += [func.count().filter(Ticket.priority == key).label(key) for key in priorities]
    columns += [
        func.count().filter(resolved).label("samples"),
        func.avg(extract("epoch", Ticket.resolved_at - Ticket.created_at) / 3600).filter(resolved).label("average"),
    ]
    result = (await db.execute(select(*columns).select_from(Ticket).where(*filters))).mappings().one()
    return DashboardView(
        total=result["total"],
        by_status={key: result[key] for key in statuses},
        by_priority={key: result[key] for key in priorities},
        resolution_samples=result["samples"],
        average_resolution_hours=None if result["average"] is None else round(float(result["average"]), 2),
    )
