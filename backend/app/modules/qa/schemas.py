from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.integrations.web_search import WebSource
from app.modules.qa.graph import Source

QuestionText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ConversationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int = Field(gt=0)
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class MessageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    text: QuestionText
    web_search: bool = False


class ConversationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    title: str
    created_at: datetime


class ConversationPage(BaseModel):
    items: list[ConversationView]
    total: int
    page: int
    page_size: int


class TokenUsage(BaseModel):
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    complete: bool
    calls: int
    known_calls: int


class MessageView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    request_id: str
    role: Literal["user", "assistant"]
    content: str
    status: Literal["submitted", "running", "answered", "clarification", "insufficient", "failed"]
    sources: list[Source | WebSource]
    web_search: bool
    error_code: str | None
    created_at: datetime
    duration_ms: int | None
    model: str | None
    prompt_version: str | None
    has_run: bool
    token_usage: TokenUsage | None


class MessagePage(BaseModel):
    items: list[MessageView]
    total: int
    page: int
    page_size: int
