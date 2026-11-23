import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.core.retrieval_settings import RetrievalSettings
from app.core.settings import Settings
from app.integrations.embeddings import EmbeddingClient, EmbeddingError
from app.integrations.knowledge_index import KnowledgeIndex
from app.models import KnowledgeChunk, KnowledgeDocument


async def main():
    parser = argparse.ArgumentParser(description="停止后端后重建已发布知识索引")
    parser.add_argument("--replace", action="store_true", help="允许替换知识索引，保留业务表和案例索引")
    args = parser.parse_args()
    config = RetrievalSettings.model_validate({})
    engine = create_database_engine(Settings.load().database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            async with await asyncio.to_thread(
                KnowledgeIndex,
                config.milvus_db_path,
                config.embedding_model,
                str(config.model_base_url),
                config.embedding_dimensions,
            ) as index:
                if await asyncio.to_thread(index.client.has_collection, "knowledge_chunks") and not args.replace:
                    raise SystemExit("知识索引已存在，请停后端后使用 --replace")
                rows = (
                    await db.execute(
                        select(KnowledgeChunk, KnowledgeDocument)
                        .join(KnowledgeDocument)
                        .where(KnowledgeDocument.status == "published")
                        .order_by(KnowledgeChunk.id)
                    )
                ).all()
                await asyncio.to_thread(index.reset)
                async with await asyncio.to_thread(
                    EmbeddingClient,
                    str(config.model_base_url),
                    config.model_api_key.get_secret_value(),
                    config.embedding_model,
                    config.embedding_dimensions,
                ) as model:
                    for start in range(0, len(rows), 10):
                        batch = rows[start : start + 10]
                        vectors = await asyncio.to_thread(
                            model.embed, [f"{doc.title}\n{chunk.content}" for chunk, doc in batch]
                        )
                        (
                            await asyncio.to_thread(
                                index.add,
                                [
                                    {
                                        "chunk_id": chunk.id,
                                        "content": f"{doc.title}\n{chunk.content}",
                                        "dense_vector": vector,
                                        "product_id": doc.product_id,
                                        "module_id": doc.module_id,
                                        "category_id": doc.category_id,
                                        "fingerprint": chunk.fingerprint,
                                    }
                                    for (chunk, doc), vector in zip(batch, vectors, strict=True)
                                ],
                            )
                        )
                        print(f"已索引 {start + len(batch)} / {len(rows)} 个知识分块", flush=True)
                await asyncio.to_thread(index.finish, len(rows))
                print("知识索引构建完成，可启动后端")
    except EmbeddingError as error:
        raise SystemExit(f"构建失败：{error}；知识索引未就绪") from None
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
