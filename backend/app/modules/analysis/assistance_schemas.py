from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
SourceId = Annotated[str, StringConstraints(pattern=r"^[TK][1-9][0-9]*$")]


class RankedSources(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    source_ids: list[SourceId] = Field(min_length=1, max_length=5)


class SuggestedStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instruction: ShortText
    source_ids: list[SourceId] = Field(min_length=1, max_length=5)


class AssistanceDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    summary: ShortText
    diagnosis: ShortText
    category_id: StrictInt
    priority: Literal["P1", "P2", "P3", "P4"]
    reason: ShortText
    steps: list[SuggestedStep] = Field(min_length=1, max_length=8)
    risks: list[ShortText] = Field(max_length=8)
    confirmations: list[ShortText] = Field(max_length=8)
    reply_subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    reply_body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=6000)]


class SourceSnapshot(BaseModel):
    source_id: SourceId
    kind: Literal["ticket", "knowledge"]
    entity_id: int
    title: str
    content: str
    fingerprint: str


class AssistanceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ticket_id: int
    draft: AssistanceDraft
    sources: list[SourceSnapshot]
    model: str
    prompt_version: str
    duration_ms: int
    created_at: datetime
    adopted_at: datetime | None
    final_solution: str | None
    final_reply: str | None


class AdoptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: Literal[True]
    solution: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
    reply: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=6000)]
