from datetime import datetime
from typing import Literal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'staff', 'customer')", name="users_role_check"),
        CheckConstraint("customer_tier BETWEEN 1 AND 4", name="users_customer_tier_check"),
        CheckConstraint("staff_level BETWEEN 1 AND 3", name="users_staff_level_check"),
        UniqueConstraint("username", name="users_username_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50))
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Literal["admin", "staff", "customer"]] = mapped_column(String(10))
    customer_tier: Mapped[int] = mapped_column(default=1, server_default="1")
    staff_level: Mapped[int] = mapped_column(default=1, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("name", name="products_name_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProductModule(Base):
    __tablename__ = "product_modules"
    __table_args__ = (UniqueConstraint("product_id", "name", name="modules_product_name_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", name="product_modules_product_id_fkey"))
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TicketCategory(Base):
    __tablename__ = "ticket_categories"
    __table_args__ = (UniqueConstraint("name", name="ticket_categories_name_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("import_key", name="tickets_import_key_key"),
        CheckConstraint("status IN ('pending', 'processing', 'resolved', 'closed')", name="tickets_status_check"),
        CheckConstraint("priority IN ('P1', 'P2', 'P3', 'P4')", name="tickets_priority_check"),
        CheckConstraint(
            "status NOT IN ('resolved', 'closed') OR length(trim(solution)) > 0",
            name="tickets_solution_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # 手动新建工单没有来源编号；CSV 记录通过唯一约束防止重复导入。
    import_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    customer_name: Mapped[str] = mapped_column(String(100))
    customer_email: Mapped[str] = mapped_column(String(320))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("product_modules.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("ticket_categories.id"), index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    required_level: Mapped[int] = mapped_column(default=1, server_default="1")
    previous_owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    priority: Mapped[str] = mapped_column(String(2), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    solution: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records: Mapped[list["TicketRecord"]] = relationship(order_by="TicketRecord.id", lazy="selectin")

    @property
    def number(self) -> str:
        return f"T{self.id:06d}"


class TicketRecord(Base):
    __tablename__ = "ticket_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeDocument(Base):
    __tablename__ = 'knowledge_documents'
    __table_args__ = (CheckConstraint("status IN ('draft','published','disabled')", name='knowledge_status_check'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    source_name: Mapped[str] = mapped_column(String(200))
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    module_id: Mapped[int] = mapped_column(ForeignKey('product_modules.id'))
    category_id: Mapped[int] = mapped_column(ForeignKey('ticket_categories.id'))
    status: Mapped[str] = mapped_column(String(20), default='draft')
    revision: Mapped[int] = mapped_column(default=1)
    chunk_count: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeChunk(Base):
    __tablename__ = 'knowledge_chunks'
    __table_args__ = (UniqueConstraint('document_id','chunk_order',name='knowledge_chunk_order_key'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey('knowledge_documents.id'), index=True)
    chunk_order: Mapped[int] = mapped_column()
    content: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64))


class AssistanceRun(Base):
    __tablename__ = 'assistance_runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey('tickets.id'), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    ticket_fingerprint: Mapped[str] = mapped_column(String(64))
    draft: Mapped[dict] = mapped_column(JSON)
    sources: Mapped[list] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(50))
    duration_ms: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    adopted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    adopted_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    final_solution: Mapped[str | None] = mapped_column(Text)
    final_reply: Mapped[str | None] = mapped_column(Text)


class BasicAnalysis(Base):
    __tablename__ = "basic_analyses"
    __table_args__ = (
        CheckConstraint("status IN ('pending','running','completed','failed')", name="basic_status_check"),
    )

    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), primary_key=True)
    attempt: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    fingerprint: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(50), default="basic-v1")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    adopted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailDelivery(Base):
    __tablename__ = "email_deliveries"
    __table_args__ = (
        CheckConstraint("status IN ('sending','accepted','failed','unknown')", name="email_status_check"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assistance_id: Mapped[int | None] = mapped_column(ForeignKey("assistance_runs.id"))
    recipient: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    message_id: Mapped[str] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QaConversation(Base):
    __tablename__ = "qa_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    title: Mapped[str] = mapped_column(String(100))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), unique=True)
    is_evaluation: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('false'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QaMessage(Base):
    __tablename__ = "qa_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "request_id", "role", name="qa_message_request_role_key"),
        CheckConstraint("role IN ('user', 'assistant')", name="qa_message_role_check"),
        CheckConstraint(
            "status IN ('submitted', 'running', 'answered', 'clarification', 'insufficient', 'failed')",
            name="qa_message_status_check",
        ),
        Index(
            "qa_one_running_per_conversation",
            "conversation_id", unique=True,
            postgresql_where=text("role = 'assistant' AND status = 'running'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("qa_conversations.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    sources: Mapped[list] = mapped_column(JSONB, default=list)
    error_code: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    duration_ms: Mapped[int | None] = mapped_column()
    run_details: Mapped[dict | None] = mapped_column(JSONB)
    web_search: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('false'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def has_run(self) -> bool:
        return self.run_details is not None

    @property
    def token_usage(self) -> dict | None:
        return self.run_details['usage']['chat'] if self.run_details is not None else None


class QaEvaluationRun(Base):
    __tablename__ = 'qa_evaluation_runs'

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    title: Mapped[str] = mapped_column(String(100))
    suite_version: Mapped[str] = mapped_column(String(50))
    cases: Mapped[list] = mapped_column(JSONB)
    results: Mapped[list] = mapped_column(JSONB, default=list)
    active_case: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
