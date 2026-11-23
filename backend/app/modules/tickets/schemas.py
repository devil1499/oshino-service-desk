from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

# Annotated 附加校验规则；Literal 限制可选值。这些规则在请求入口执行。
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
CustomerName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Priority = Literal["P1", "P2", "P3", "P4"]
TicketStatus = Literal["pending", "processing", "resolved", "closed"]
PositiveId = Annotated[int, Field(gt=0)]


class TicketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title
    description: Description
    customer_name: CustomerName
    customer_email: EmailStr
    product_id: PositiveId
    module_id: PositiveId
    category_id: PositiveId
    priority: Priority


class TicketPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title | None = None
    description: Description | None = None
    customer_name: CustomerName | None = None
    customer_email: EmailStr | None = None
    product_id: PositiveId | None = None
    module_id: PositiveId | None = None
    category_id: PositiveId | None = None
    owner_id: PositiveId | None = None
    priority: Priority | None = None

    @model_validator(mode="after")
    def reject_empty_changes(self) -> Self:
        # PATCH 中省略字段表示不修改；显式 null 不能清空这些必填字段。
        if not self.model_fields_set:
            raise ValueError("至少提交一个需要修改的字段")
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} 不能设为 null")
        return self


class NoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: Description


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    solution: Description


class CloseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_reply_confirmed: Literal[True]


class RecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    author_id: int
    kind: str
    content: str
    created_at: datetime


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    number: str
    title: str
    description: str
    customer_name: str
    customer_email: str
    product_id: int
    module_id: int
    category_id: int
    owner_id: int | None
    priority: Priority
    status: TicketStatus
    solution: str
    created_at: datetime
    updated_at: datetime


class TicketDetail(TicketResponse):
    records: list[RecordResponse]


class TicketPage(BaseModel):
    items: list[TicketResponse]
    total: int
    page: int
    page_size: int
