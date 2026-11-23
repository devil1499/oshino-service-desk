from uuid import uuid4

import pytest
from test_qa_api import qa as qa
from test_similar import retrieval as retrieval
from test_postgres_foundation import database as database

from app.core.ai_settings import get_ai_store, AiSettingsInput
from app.integrations.web_search import WebSearchClient, WebSearchError, WebSource
from app.modules.qa.router import get_chat_client

pytestmark = pytest.mark.postgres


async def test_web_answer_sources_and_trace_are_saved_and_request_mode_cannot_change(qa, monkeypatch, tmp_path):
    app, client, headers, catalog, document, calls = qa
    monkeypatch.setenv("AI_SETTINGS_PATH", str(tmp_path / "ai.json"))
    get_ai_store().save(
        AiSettingsInput(
            chat_base_url="https://api.deepseek.com", chat_model="test", chat_api_key="test-key", search_enabled=True
        )
    )
    searched = []

    async def search(self, query):
        searched.append(query)
        return [
            WebSource(
                source_id="W1",
                title="网页帮助",
                content="通过官方流程处理登录问题",
                url="https://help.example.com/login",
                retrieved_at="2026-11-04T00:00:00Z",
            )
        ]

    monkeypatch.setattr(WebSearchClient, "search", search)

    class Model:
        model = "test"

        def ask(self, instruction, data, result_type):
            if result_type.__name__ == "Plan":
                return result_type(action="search", text="登录失败")
            return result_type(action="answer", text="有依据", paragraphs=[{"text": "可参考网页帮助。", "source_ids": ["W1"]}])

    app.dependency_overrides[get_chat_client] = lambda: Model()
    conversation = (
        await client.post(
            "/api/qa/conversations", headers=headers, json={"product_id": catalog["product_id"], "title": "联网测试"}
        )
    ).json()
    path = f"/api/qa/conversations/{conversation['id']}/messages"
    body = {"request_id": str(uuid4()), "text": "登录失败", "web_search": True}
    response = await client.post(path, headers=headers, json=body)
    assert response.status_code == 201, response.text
    answer = response.json()
    assert answer["web_search"] is True
    assert answer["sources"][0]["url"] == "https://help.example.com/login"
    trace = (await client.get(f"{path}/{answer['id']}/run", headers=headers)).json()
    step = next(step for step in trace["steps"] if step["name"] == "web_search")
    assert step["status"] == "succeeded"
    assert step["output"]["result_count"] == 1
    assert trace["usage"]["chat"]["calls"] == 2
    assert len(searched) == 1
    assert (await client.post(path, headers=headers, json=body)).json() == answer
    assert (await client.post(path, headers=headers, json={**body, "web_search": False})).status_code == 409
    assert len(searched) == 1

    async def broken(self, query):
        raise WebSearchError("DeepSeek 搜索返回 HTTP 402；余额不足")

    monkeypatch.setattr(WebSearchClient, "search", broken)
    failed = await client.post(path, headers=headers, json={**body, "request_id": str(uuid4())})
    assert failed.status_code == 502, failed.text
    history = (await client.get(path, headers=headers)).json()["items"]
    assert history[-1]["status"] == "failed"
    assert "402" in history[-1]["content"]
