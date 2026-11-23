import asyncio

from alembic import context
from pydantic import SecretStr
from sqlalchemy import Connection

from app import models  # noqa: F401 — 注册本阶段的数据表
from app.core.database import Base, create_database_engine
from app.core.settings import Settings


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def migration_url() -> SecretStr:
    database_url = context.config.attributes.get("database_url")
    if database_url is None:
        return Settings.load().database_url
    # 隔离测试通过 Config 传入连接地址，不修改进程环境或业务配置。
    return SecretStr(str(database_url))


async def online() -> None:
    engine = create_database_engine(migration_url())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=migration_url().get_secret_value(),
        target_metadata=Base.metadata, literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
