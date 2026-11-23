from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import cast
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.core.errors import install_error_handlers
from app.core.passwords import PasswordService
from app.core.settings import Settings
from app.modules.ai_service import router as ai_service_router
from app.modules.analysis.assistance import router as assistance_router
from app.modules.analysis.basic import interrupt_analyses
from app.modules.analysis.basic import router as basic_analysis_router
from app.modules.analysis.evaluation import router as evaluation_router
from app.modules.analysis.router import router as analysis_router
from app.modules.config.router import router as config_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.email.router import interrupt_deliveries
from app.modules.email.router import router as email_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.knowledge.search import router as knowledge_search_router
from app.modules.qa.router import router as qa_router
from app.modules.qa.service import interrupt_questions
from app.modules.qa.evaluation import interrupt_evaluations
from app.modules.qa.evaluation import router as qa_evaluation_router
from app.modules.tickets.import_csv import router as import_router
from app.modules.tickets.router import router as tickets_router
from app.modules.users.router import router as users_router
from app.modules.service_portal import router as service_router


def create_app(settings: Settings | None = None, *, recover_jobs: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        config = settings if settings is not None else Settings.load()
        app.state.settings = config
        engine = create_database_engine(config.database_url)
        app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        app.state.passwords = PasswordService()
        try:
            if recover_jobs:
                await interrupt_analyses(app.state.session_factory)
                await interrupt_deliveries(app.state.session_factory)
                await interrupt_questions(app.state.session_factory)
                await interrupt_evaluations(app.state.session_factory)
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="售后工单智能辅助系统", lifespan=lifespan)

    @app.middleware("http")
    async def request_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request.state.request_id = uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = cast(str, request.state.request_id)
        return response

    install_error_handlers(app)
    app.include_router(users_router)
    app.include_router(service_router)
    app.include_router(config_router)
    app.include_router(import_router)
    app.include_router(tickets_router)
    app.include_router(analysis_router)
    app.include_router(basic_analysis_router)
    app.include_router(assistance_router)
    app.include_router(evaluation_router)
    app.include_router(dashboard_router)
    app.include_router(email_router)
    app.include_router(knowledge_router)
    app.include_router(knowledge_search_router)
    app.include_router(qa_router)
    app.include_router(qa_evaluation_router)
    app.include_router(ai_service_router)

    @app.get("/api/health", tags=["健康检查"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
