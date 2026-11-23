from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class NamedCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name


class NamedUpdate(NamedCreate):
    is_active: bool


class NamedResponse(NamedUpdate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ModuleCreate(NamedCreate):
    product_id: int = Field(gt=0)


class ModuleResponse(NamedResponse):
    product_id: int
