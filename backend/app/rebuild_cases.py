import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.core.retrieval_settings import RetrievalSettings
from app.core.settings import Settings
from app.integrations.case_index import CaseIndex
from app.integrations.embeddings import EmbeddingClient, EmbeddingError
from app.models import Ticket
from app.modules.analysis.cases import case_row, case_text


async def main() -> None:
    parser = argparse.ArgumentParser(description="后端停止后，全量重建有效历史案例索引")
    parser.add_argument("--replace", action="store_true", help="允许替换已有派生索引，PostgreSQL 工单不变")
    args = parser.parse_args()
    config = RetrievalSettings.model_validate({})
    engine = create_database_engine(Settings.load().database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            async with await asyncio.to_thread(
                CaseIndex,
                config.milvus_db_path,
                config.embedding_model,
                str(config.model_base_url),
                config.embedding_dimensions,
            ) as index:
                if await asyncio.to_thread(index.client.has_collection, "ticket_cases") and not args.replace:
                    raise SystemExit("索引已存在；请停后端并加 --replace 重建")
                tickets = (
                    await db.scalars(
                        select(Ticket)
                        .where(
                            Ticket.status.in_(["resolved", "closed"]),
                            Ticket.solution != "",
                        )
                        .order_by(Ticket.id)
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
                    # 每批 10 条，同时兼容本教程所用接口的请求批量上限。
                    for start in range(0, len(tickets), 10):
                        batch = tickets[start : start + 10]
                        vectors = await asyncio.to_thread(model.embed, [case_text(ticket) for ticket in batch])
                        await asyncio.to_thread(
                            index.add, [case_row(ticket, vector) for ticket, vector in zip(batch, vectors, strict=True)]
                        )
                        print(f"已写入 {start + len(batch)} / {len(tickets)} 条有效案例", flush=True)
                await asyncio.to_thread(index.finish, len(tickets))
                print(f"索引构建完成：{len(tickets)} 条。可以重新启动后端。")
    except EmbeddingError as error:
        raise SystemExit(f"构建失败：{error}。索引未就绪，修正后重新执行 --replace。") from None
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
