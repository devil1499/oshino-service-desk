from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Content = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100000)]


class DocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title
    content: Content
    product_id: int = Field(gt=0)
    module_id: int = Field(gt=0)
    category_id: int = Field(gt=0)


class DocumentView(DocumentInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_name: str
    status: Literal["draft", "published", "disabled"]
    revision: int
    chunk_count: int
    updated_at: datetime


class DocumentPage(BaseModel):
    items: list[DocumentView]
    total: int
    page: int
