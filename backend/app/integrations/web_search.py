"""DeepSeek 独立搜索；只接受搜索返回的网页来源，不下载任意 URL。"""

from datetime import UTC, datetime
from typing import Literal

import httpx2 as httpx
from pydantic import BaseModel, Field, HttpUrl, ValidationError, field_validator

SEARCH_URL = "https://api.deepseek.com/v1/tools/search"


class WebSource(BaseModel):
    kind: Literal["web"] = "web"
    source_id: str
    title: str
    content: str
    url: HttpUrl
    retrieved_at: str

    @field_validator("url")
    @classmethod
    def safe_link(cls, value):
        if value.username or value.password:
            raise ValueError("来源链接不得包含凭据")
        return value


class SearchResult(BaseModel):
    title: str = Field(min_length=1)
    url: HttpUrl
    summary: str = Field(min_length=1)


class SearchResponse(BaseModel):
    results: list[SearchResult] = Field(max_length=5)


class WebSearchError(RuntimeError):
    pass


class WebSearchClient:
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self.api_key = api_key
        self.client = client if client is not None else httpx.AsyncClient(timeout=20, follow_redirects=False)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.client.aclose()

    async def search(self, query: str) -> list[WebSource]:
        if not query.strip() or len(query) > 128:
            raise WebSearchError("联网搜索词必须为 1～128 个字符")
        try:
            response = await self.client.post(
                SEARCH_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"query": query, "count": 5, "need_content": False},
            )
            response.raise_for_status()
        except httpx.TimeoutException as error:
            raise WebSearchError("DeepSeek 联网搜索超过20秒") from error
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            reasons = {401: "请检查 DeepSeek API 密钥", 402: "DeepSeek 账户余额不足", 429: "搜索请求过于频繁"}
            raise WebSearchError(
                f"DeepSeek 搜索返回 HTTP {status}；" + reasons.get(status, "搜索服务暂时不可用")
            ) from error
        except httpx.RequestError as error:
            raise WebSearchError("无法连接 DeepSeek 搜索服务，请检查网络") from error
        try:
            results = SearchResponse.model_validate(response.json()).results
            now = datetime.now(UTC).isoformat()
            return [
                WebSource(source_id=f"W{i + 1}", title=row.title, content=row.summary, url=row.url, retrieved_at=now)
                for i, row in enumerate(results)
            ]
        except (ValidationError, ValueError) as error:
            raise WebSearchError("DeepSeek 搜索结果格式不符合约定") from error
