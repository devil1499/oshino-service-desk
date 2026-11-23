import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.retrieval_settings import RetrievalSettings
from app.core.security import CurrentUser, DbSession
from app.integrations.embeddings import EmbeddingClient, EmbeddingError
from app.integrations.hybrid_index import IndexNotReady
from app.integrations.knowledge_index import KnowledgeIndex
from app.models import KnowledgeChunk, KnowledgeDocument, Ticket
from app.modules.analysis.router import RetrievalConfig, get_embedding_client
from app.modules.knowledge.text import document_fingerprint
from app.modules.tickets.service import get_ticket

router = APIRouter(prefix="/api/tickets", tags=["知识检索"])


class KnowledgeHit(BaseModel):
    document_id: int
    chunk_id: int
    title: str
    source_name: str
    chunk_order: int
    content: str
    fingerprint: str
    score: float
    scope: Literal["module", "category"]


class KnowledgeResult(BaseModel):
    items: list[KnowledgeHit]
    expanded: bool
    stale_count: int
    indexed_at: str


async def search_knowledge(
    ticket: Ticket, db: AsyncSession, config: RetrievalSettings, model: EmbeddingClient
) -> KnowledgeResult:
    query = f"标题：{ticket.title}\n问题：{ticket.description[:3000]}"
    async with await asyncio.to_thread(
        KnowledgeIndex,
        config.milvus_db_path,
        config.embedding_model,
        str(config.model_base_url),
        config.embedding_dimensions,
    ) as index:
        metadata = await asyncio.to_thread(index.ready)
        if metadata["count"] == 0:
            return KnowledgeResult(items=[], expanded=False, stale_count=0, indexed_at=metadata["built_at"])
        vector = (await asyncio.to_thread(model.embed, [query]))[0]
        items, seen = [], set()
        stale_count = 0
        expanded = False
        scopes: list[tuple[Literal["module", "category"], str]] = [
            ("module", f"product_id == {ticket.product_id} and module_id == {ticket.module_id}"),
            ("category", f"category_id == {ticket.category_id}"),
        ]
        for scope, expression in scopes:
            if scope == "category":
                expanded = True
            for hit in await asyncio.to_thread(index.search, query, vector, expression):
                chunk_id = int(hit["chunk_id"])
                if chunk_id in seen:
                    continue
                seen.add(chunk_id)
                chunk = await db.get(KnowledgeChunk, chunk_id)
                if chunk is None:
                    stale_count += 1
                    continue
                doc = await db.get(KnowledgeDocument, chunk.document_id)
                if (
                    doc is None
                    or doc.status != "published"
                    or document_fingerprint(doc) != hit["entity"]["fingerprint"]
                ):
                    stale_count += 1
                    continue
                items.append(
                    KnowledgeHit(
                        document_id=doc.id,
                        chunk_id=chunk.id,
                        title=doc.title,
                        source_name=doc.source_name,
                        chunk_order=chunk.chunk_order,
                        content=chunk.content,
                        fingerprint=chunk.fingerprint,
                        score=hit["distance"],
                        scope=scope,
                    )
                )
                if len(items) == 5:
                    break
            if len(items) == 5:
                break
    return KnowledgeResult(items=items, expanded=expanded, stale_count=stale_count, indexed_at=metadata["built_at"])


@router.post("/{ticket_id}/knowledge", response_model=KnowledgeResult)
async def find_knowledge(
    ticket_id: int,
    db: DbSession,
    user: CurrentUser,
    config: RetrievalConfig,
    model: Annotated[EmbeddingClient, Depends(get_embedding_client)],
):
    ticket = await get_ticket(db, ticket_id)
    try:
        return await search_knowledge(ticket, db, config, model)
    except IndexNotReady as error:
        raise HTTPException(503, str(error)) from error
    except EmbeddingError as error:
        raise HTTPException(502, str(error)) from error
