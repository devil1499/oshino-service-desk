import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from app.core.retrieval_settings import RetrievalSettings
from app.core.security import CurrentUser, DbSession
from app.integrations.case_index import CaseIndex, IndexNotReady
from app.integrations.embeddings import EmbeddingClient, EmbeddingError
from app.models import Ticket
from app.modules.analysis.cases import case_fingerprint
from app.modules.tickets.service import get_ticket

router = APIRouter(prefix="/api/tickets", tags=["相似案例"])


def get_retrieval_settings() -> RetrievalSettings:
    try:
        return RetrievalSettings.model_validate({})
    except ValidationError as error:
        fields = ", ".join(".".join(map(str, item["loc"])) for item in error.errors())
        raise HTTPException(503, f"检索配置缺失或不合法，请检查 backend/.env.retrieval：{fields}") from error


RetrievalConfig = Annotated[RetrievalSettings, Depends(get_retrieval_settings)]


def get_embedding_client(config: RetrievalConfig):
    with EmbeddingClient(
        str(config.model_base_url),
        config.model_api_key.get_secret_value(),
        config.embedding_model,
        config.embedding_dimensions,
    ) as model:
        yield model


class SimilarCase(BaseModel):
    id: int
    number: str
    title: str
    module_id: int
    solution: str
    score: float
    scope: Literal["module", "category"]


class SimilarResult(BaseModel):
    items: list[SimilarCase]
    expanded: bool
    stale_count: int
    indexed_at: str


@router.post("/{ticket_id}/similar", response_model=SimilarResult)
async def similar_cases(
    ticket_id: int,
    db: DbSession,
    user: CurrentUser,
    config: RetrievalConfig,
    model: Annotated[EmbeddingClient, Depends(get_embedding_client)],
    mode: Literal["bm25", "dense", "hybrid"] = "hybrid",
):
    ticket = await get_ticket(db, ticket_id)
    query = f"标题：{ticket.title}\n问题：{ticket.description[:3000]}"
    items = []
    seen = {ticket_id}
    stale_count = 0
    try:
        async with await asyncio.to_thread(
            CaseIndex,
            config.milvus_db_path,
            config.embedding_model,
            str(config.model_base_url),
            config.embedding_dimensions,
        ) as index:
            metadata = await asyncio.to_thread(index.ready)
            if metadata["count"] == 0:
                return SimilarResult(items=[], expanded=False, stale_count=0, indexed_at=metadata["built_at"])
            vector = [] if mode == "bm25" else (await asyncio.to_thread(model.embed, [query]))[0]
            scopes: list[tuple[Literal["module", "category"], str]] = [
                ("module", f"product_id == {ticket.product_id} and module_id == {ticket.module_id}"),
                ("category", f"category_id == {ticket.category_id}"),
            ]
            expanded = False
            for scope, expression in scopes:
                if scope == "category":
                    expanded = True
                expression += f" and ticket_id != {ticket_id}"
                for hit in await asyncio.to_thread(index.search, query, vector, expression, mode):
                    case_id = int(hit["ticket_id"])
                    if case_id in seen:
                        continue
                    seen.add(case_id)
                    case = await db.get(Ticket, case_id)
                    if (
                        case is None
                        or case.status not in {"resolved", "closed"}
                        or not case.solution.strip()
                        or case_fingerprint(case) != hit["entity"]["fingerprint"]
                    ):
                        stale_count += 1
                        continue
                    items.append(
                        SimilarCase(
                            id=case.id,
                            number=case.number,
                            title=case.title,
                            module_id=case.module_id,
                            solution=case.solution,
                            score=hit["distance"],
                            scope=scope,
                        )
                    )
                    if len(items) == 5:
                        break
                if len(items) == 5:
                    break
    except IndexNotReady as error:
        raise HTTPException(503, str(error)) from error
    except EmbeddingError as error:
        raise HTTPException(502, str(error)) from error
    return SimilarResult(items=items, expanded=expanded, stale_count=stale_count, indexed_at=metadata["built_at"])
