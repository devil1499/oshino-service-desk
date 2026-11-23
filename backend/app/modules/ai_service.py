import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.ai_settings import AiConfigurationError, AiSettingsInput, AiSettingsStore, get_ai_store
from app.core.security import AdminUser, CurrentUser
from app.integrations.chat import ChatClient, ChatError
from app.integrations.web_search import WebSearchClient, WebSearchError

router = APIRouter(prefix="/api/ai-service", tags=["AI服务"])
Store = Annotated[AiSettingsStore, Depends(get_ai_store)]


@router.get("/settings")
def settings(user: AdminUser, store: Store):
    try:
        return store.view()
    except AiConfigurationError as error:
        raise HTTPException(503, str(error)) from error


@router.put("/settings")
def save_settings(body: AiSettingsInput, user: AdminUser, store: Store):
    try:
        return store.save(body)
    except AiConfigurationError as error:
        raise HTTPException(422, str(error)) from error
    except OSError as error:
        raise HTTPException(503, "AI 配置保存失败，请检查私有目录是否可写") from error


@router.get("/capabilities")
def capabilities(user: CurrentUser, store: Store):
    try:
        return {"web_search_available": store.view()["search_enabled"]}
    except AiConfigurationError as error:
        raise HTTPException(503, str(error)) from error


class Probe(BaseModel):
    answer: str = Field(min_length=1)


@router.post("/test-chat")
async def test_chat(user: AdminUser, store: Store):
    try:
        config = await asyncio.to_thread(store.chat)
        async with ChatClient(
            str(config.chat_base_url), config.chat_api_key.get_secret_value(), config.chat_model
        ) as client:
            await asyncio.to_thread(client.ask, '连接检查，请返回 {"answer":"ok"}。', {"question": "连接检查"}, Probe)
        return {"message": "聊天接口连接及 JSON 输出检查通过"}
    except AiConfigurationError as error:
        raise HTTPException(503, str(error)) from error
    except ChatError as error:
        raise HTTPException(502, str(error)) from error


@router.post("/test-search")
async def test_search(user: AdminUser, store: Store):
    try:
        key = await asyncio.to_thread(store.search_key)
        async with WebSearchClient(key) as client:
            sources = await client.search("Python 官方文档 site:docs.python.org")
        return {
            "message": f"搜索接口正常，返回 {len(sources)} 条结果",
            "sources": [source.model_dump(mode="json") for source in sources],
        }
    except AiConfigurationError as error:
        raise HTTPException(503, str(error)) from error
    except WebSearchError as error:
        raise HTTPException(502, str(error)) from error
