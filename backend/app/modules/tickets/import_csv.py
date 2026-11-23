import csv
import io
from typing import Annotated, Literal, Self

from fastapi import APIRouter, HTTPException, UploadFile
from psycopg.errors import UniqueViolation
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    StringConstraints,
    ValidationError,
    model_validator,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.security import AdminUser, DbSession
from app.models import Product, ProductModule, Ticket, TicketCategory
from app.modules.tickets.schemas import CustomerName, Description, Priority, Title
from app.modules.tickets.service import add_record, validate_catalog

router = APIRouter(prefix="/api/tickets", tags=["CSV 导入"])
MAX_BYTES = 4 * 1024 * 1024
MAX_ROWS = 5000
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ImportRow(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    import_key: Name
    title: Title
    description: Description
    customer_name: CustomerName
    customer_email: EmailStr
    product: Name
    module: Name
    category: Name
    priority: Priority
    status: Literal["pending", "resolved"]
    solution: Annotated[str, StringConstraints(strip_whitespace=True, max_length=10000)]

    @model_validator(mode="after")
    def check_solution(self) -> Self:
        if self.status == "resolved" and not self.solution:
            raise ValueError("已解决工单必须填写解决方案")
        if self.status == "pending" and self.solution:
            raise ValueError("待处理工单的解决方案应为空")
        return self


class ImportResult(BaseModel):
    imported: int
    ticket_ids: list[int]


def parse_csv(content: bytes) -> list[ImportRow]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HTTPException(422, "CSV 必须保存为 UTF-8 编码") from error
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    rows = []
    keys = set()
    try:
        if reader.fieldnames != list(ImportRow.model_fields):
            raise HTTPException(422, "CSV 表头与模板不一致，请保留字段顺序和英文名称")
        for number, values in enumerate(reader, start=1):
            if number > MAX_ROWS:
                raise HTTPException(422, f"每次最多导入 {MAX_ROWS} 条记录")
            if None in values or None in values.values():
                raise HTTPException(422, f"第 {number} 条记录的列数与表头不一致")
            try:
                row = ImportRow.model_validate(values)
            except ValidationError as error:
                reasons = "；".join(
                    f"{'.'.join(map(str, item['loc'])) or '记录'}: {item['msg']}" for item in error.errors()
                )
                raise HTTPException(422, f"第 {number} 条记录：{reasons}") from error
            if row.import_key in keys:
                raise HTTPException(409, f"第 {number} 条记录的 import_key 在文件内重复")
            keys.add(row.import_key)
            rows.append(row)
    except csv.Error as error:
        raise HTTPException(422, f"CSV 第 {reader.line_num} 行格式错误：{error}") from error
    if not rows:
        raise HTTPException(422, "CSV 没有数据记录")
    return rows


@router.post("/import", response_model=ImportResult, status_code=201)
async def import_tickets(file: UploadFile, db: DbSession, user: AdminUser):
    # UploadFile 由 FastAPI 关闭；有界读取避免把任意大小的文件全部装入内存。
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "CSV 不能超过 4 MiB")
    rows = parse_csv(content)
    existing = set(
        await db.scalars(select(Ticket.import_key).where(Ticket.import_key.in_([row.import_key for row in rows])))
    )
    products = {item.name: item for item in (await db.scalars(select(Product)))}
    modules = {(item.product_id, item.name): item for item in (await db.scalars(select(ProductModule)))}
    categories = {item.name: item for item in (await db.scalars(select(TicketCategory)))}
    tickets = []
    for number, row in enumerate(rows, start=1):
        if row.import_key in existing:
            raise HTTPException(409, f"第 {number} 条记录已经导入，请勿重复上传")
        product = products.get(row.product)
        category = categories.get(row.category)
        module = modules.get((product.id, row.module)) if product is not None else None
        if product is None or category is None or module is None:
            raise HTTPException(422, f"第 {number} 条记录：产品、所属模块或分类名称不存在")
        try:
            await validate_catalog(db, product.id, module.id, category.id)
        except HTTPException as error:
            raise HTTPException(error.status_code, f"第 {number} 条记录：{error.detail}") from error
        ticket = Ticket(
            **row.model_dump(exclude={"product", "module", "category"}),
            product_id=product.id,
            module_id=module.id,
            category_id=category.id,
            owner_id=user.id,
        )
        add_record(ticket, user.id, "imported", "管理员导入历史记录；时间为导入时间，非原始处理时间")
        tickets.append(ticket)
    db.add_all(tickets)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        if isinstance(error.orig, UniqueViolation) and error.orig.diag.constraint_name == "tickets_import_key_key":
            raise HTTPException(409, "这些编号已被另一个请求导入，本批未写入") from error
        raise
    return ImportResult(imported=len(tickets), ticket_ids=[ticket.id for ticket in tickets])
