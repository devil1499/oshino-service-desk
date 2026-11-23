import pytest
from test_postgres_foundation import database as database
from test_tickets import ticket_context as ticket_context

from app.integrations.chat import ChatClient, ChatError

pytestmark = [pytest.mark.postgres, pytest.mark.basic_analysis]


async def test_new_ticket_analysis_requires_human_adoption(ticket_context, monkeypatch):
    client, headers, body = ticket_context
    monkeypatch.setenv("CHAT_BASE_URL", "https://model.example/v1")
    monkeypatch.setenv("CHAT_API_KEY", "test-key")
    monkeypatch.setenv("CHAT_MODEL", "test-model")

    def answer(self, instruction, data, result_type):
        return result_type(
            summary="账号登录失败", category_id=body["category_id"], priority="P1", reason="关键功能不可用"
        )

    monkeypatch.setattr(ChatClient, "ask", answer)
    created = await client.post("/api/tickets", headers=headers, json=body)
    assert created.status_code == 201, created.text
    path = f"/api/tickets/{created.json()['id']}"
    analysis = await client.get(path + "/analysis", headers=headers)
    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["status"] == "completed"
    assert analysis.json()["result"]["priority"] == "P1"
    assert (await client.get(path, headers=headers)).json()["priority"] == body["priority"]
    assert (await client.post(path + "/analysis/adopt", headers=headers, json={"confirmed": False})).status_code == 422
    adopted = await client.post(path + "/analysis/adopt", headers=headers, json={"confirmed": True})
    assert adopted.status_code == 200, adopted.text
    assert (await client.get(path, headers=headers)).json()["priority"] == "P1"
    assert (await client.post(path + "/analysis/adopt", headers=headers, json={"confirmed": True})).status_code == 409


async def test_model_failure_keeps_the_new_ticket(ticket_context, monkeypatch):
    client, headers, body = ticket_context
    monkeypatch.setenv("CHAT_BASE_URL", "https://model.example/v1")
    monkeypatch.setenv("CHAT_API_KEY", "test-key")
    monkeypatch.setenv("CHAT_MODEL", "test-model")

    def fail(self, instruction, data, result_type):
        raise ChatError("模拟模型暂时不可用")

    monkeypatch.setattr(ChatClient, "ask", fail)
    created = await client.post("/api/tickets", headers=headers, json=body)
    assert created.status_code == 201, created.text
    path = f"/api/tickets/{created.json()['id']}"
    analysis = (await client.get(path + "/analysis", headers=headers)).json()
    assert analysis["status"] == "failed"
    assert analysis["error"] == "模拟模型暂时不可用"
    assert (await client.get(path, headers=headers)).status_code == 200
