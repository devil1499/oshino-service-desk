from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def create_database_engine(database_url: SecretStr) -> AsyncEngine:
    return create_async_engine(
        database_url.get_secret_value(),
        connect_args={"connect_timeout": 5, "options": "-c timezone=UTC -c statement_timeout=10000"},
        hide_parameters=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=5,
    )

def get_session_factory(request: Request)-> async_sessionmaker[AsyncSession]:
    return cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)

SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]

async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    # Starlette 的 state 是动态边界，在这里恢复集中接线时确定的类型。
    factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    async with factory() as session:
        yield session
