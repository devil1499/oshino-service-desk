import asyncio
from functools import partial
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ai_settings import get_ai_store
from app.core.retrieval_settings import RetrievalSettings
from app.integrations.chat import ChatClient
from app.integrations.embeddings import EmbeddingClient
from app.integrations.hybrid_index import IndexNotReady
from app.integrations.knowledge_index import KnowledgeIndex
from app.integrations.web_search import WebSearchClient
from app.models import KnowledgeChunk, KnowledgeDocument
from app.modules.knowledge.text import document_fingerprint
from app.modules.qa.graph import Source
from app.modules.qa.trace import redact


def web_search_adapter(trace=None):
    async def search(query: str):
        safe_query = redact(query)

        async def execute(data):
            key = await asyncio.to_thread(get_ai_store().search_key)
            async with WebSearchClient(key) as client:
                sources = await client.search(data['query'])
            return {'sources': sources, 'result_count': len(sources)}

        result = (await trace.run_step('web_search', execute, {'query': safe_query})
                  if trace is not None else await execute({'query': safe_query}))
        return result['sources']
    return search


def model_adapter(chat: ChatClient, trace=None):
    async def call(instruction, data, result_type):
        operation = chat.ask
        if isinstance(chat, ChatClient) and result_type.__name__ == 'Plan' and urlsplit(str(chat.client.base_url)).hostname == 'api.deepseek.com':
            operation = partial(chat.ask, thinking=False)
        if trace is not None:
            return await trace.call('chat', chat.model, operation, instruction, data, result_type)
        return await asyncio.to_thread(operation, instruction, data, result_type)

    return call


def search_adapter(
    config: RetrievalSettings,
    embedding: EmbeddingClient,
    session_factory: async_sessionmaker[AsyncSession],
    trace=None,
):
    async def search(query: str, product_id: int) -> list[Source]:
        async with await asyncio.to_thread(
            KnowledgeIndex,
            config.milvus_db_path,
            config.embedding_model,
            str(config.model_base_url),
            config.embedding_dimensions,
        ) as index:
            metadata = await asyncio.to_thread(index.ready)
            if metadata["count"] == 0:
                async with session_factory() as db:
                    published = await db.scalar(
                        select(KnowledgeDocument.id).where(
                            KnowledgeDocument.product_id == product_id,
                            KnowledgeDocument.status == "published",
                        ).limit(1)
                    )
                if published is not None:
                    raise IndexNotReady("已发布知识尚未写入索引，请重建知识索引")
                return []
            vectors = (await trace.call('embedding', config.embedding_model, embedding.embed, [query])
                       if trace is not None else await asyncio.to_thread(embedding.embed, [query]))
            vector = vectors[0]
            hits = await asyncio.to_thread(index.search, query, vector, f"product_id == {product_id}")

        ids = [int(hit["chunk_id"]) for hit in hits]
        if not ids:
            return []
        async with session_factory() as db:
            rows = (
                await db.execute(
                    select(KnowledgeChunk, KnowledgeDocument)
                    .join(KnowledgeDocument)
                    .where(KnowledgeChunk.id.in_(ids))
                )
            ).all()
        by_id = {chunk.id: (chunk, document) for chunk, document in rows}
        sources = []
        stale_hits = 0
        for hit in hits:
            chunk_id = int(hit["chunk_id"])
            pair = by_id.get(chunk_id)
            if pair is None:
                stale_hits += 1
                continue
            chunk, document = pair
            fingerprint = document_fingerprint(document)
            if (
                document.status != "published"
                or document.product_id != product_id
                or fingerprint != chunk.fingerprint
                or fingerprint != hit["entity"]["fingerprint"]
            ):
                stale_hits += 1
                continue
            sources.append(Source(
                source_id=f"K{chunk.id}", document_id=document.id, chunk_id=chunk.id,
                title=document.title, content=chunk.content, fingerprint=fingerprint,
            ))
            if len(sources) == 5:
                break
        if not sources and stale_hits:
            raise IndexNotReady("知识索引命中已失效资料，请重建知识索引")
        return sources

    return search
