import json

import httpx2 as httpx
import pytest

from app.integrations.web_search import WebSearchClient, WebSearchError


async def test_search_uses_real_contract_and_returns_traceable_sources():
    def handler(request):
        assert str(request.url) == "https://api.deepseek.com/v1/tools/search"
        assert request.headers["Authorization"] == "Bearer search-fixture-key"
        assert json.loads(request.content) == {"query": "登录失败", "count": 5, "need_content": False}
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "官方帮助",
                        "url": "https://help.example.com/login",
                        "summary": "通过官方流程找回密码。",
                    }
                ]
            },
        )

    async with WebSearchClient(
        "search-fixture-key", httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ) as client:
        sources = await client.search("登录失败")
    assert sources[0].kind == "web"
    assert sources[0].source_id == "W1"
    assert sources[0].content == "通过官方流程找回密码。"
    assert sources[0].retrieved_at


@pytest.mark.parametrize("status", [401, 402, 429, 500])
async def test_search_errors_are_visible_and_never_retried(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "do not leak upstream body"}})

    async with WebSearchClient("secret", httpx.AsyncClient(transport=httpx.MockTransport(handler))) as client:
        with pytest.raises(WebSearchError, match=f"HTTP {status}"):
            await client.search("登录")
    assert len(calls) == 1


async def test_search_refuses_unsafe_source_links():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"results": [{"title": "unsafe", "url": "javascript:alert(1)", "summary": "content"}]}
        )
    )
    async with WebSearchClient("secret", httpx.AsyncClient(transport=transport)) as client:
        with pytest.raises(WebSearchError, match="结果格式"):
            await client.search("登录")


async def test_search_timeout_and_empty_results_are_not_fabricated_answers():
    def timeout(request):
        raise httpx.ReadTimeout('test timeout', request=request)
    async with WebSearchClient('secret', httpx.AsyncClient(transport=httpx.MockTransport(timeout))) as client:
        with pytest.raises(WebSearchError, match='20秒'):
            await client.search('登录')
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'results': []}))
    async with WebSearchClient('secret', httpx.AsyncClient(transport=transport)) as client:
        assert await client.search('没有结果的问题') == []
