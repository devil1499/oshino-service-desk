from uuid import uuid4

import pytest
from test_postgres_foundation import database as database
from test_tickets import ticket_context as ticket_context

from app.integrations import smtp

pytestmark = pytest.mark.postgres


async def test_confirmed_test_email_is_sent_once_and_recorded(ticket_context, monkeypatch):
    client, headers, ticket_body = ticket_context
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_SECURITY", "ssl")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "test-authorization-code")
    monkeypatch.setenv("SMTP_FROM", "sender@example.com")
    monkeypatch.setenv("SMTP_TEST_RECIPIENTS", "inbox@example.com")
    sent = []
    monkeypatch.setattr(smtp, "deliver", lambda config, message: sent.append(message), raising=False)
    ticket = (await client.post("/api/tickets", headers=headers, json=ticket_body)).json()
    path = f"/api/tickets/{ticket['id']}/emails"
    body = {
        "request_id": str(uuid4()), "recipient": "inbox@example.com", "subject": "处理说明",
        "content": "请核对登录状态。", "confirmed": True,
    }
    assert (await client.post(path, headers=headers, json={**body, "confirmed": False})).status_code == 422
    refused = await client.post(path, headers=headers, json={**body, "recipient": "other@example.com"})
    assert refused.status_code == 422
    first = await client.post(path, headers=headers, json=body)
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "accepted"
    assert len(sent) == 1
    assert (await client.post(path, headers=headers, json=body)).json()["id"] == first.json()["id"]
    assert len(sent) == 1
    assert (await client.post(path, headers=headers, json={**body, "subject": "另一封"})).status_code == 409
    assert len((await client.get(path, headers=headers)).json()) == 1


async def test_missing_smtp_config_creates_no_delivery(ticket_context, monkeypatch):
    client, headers, ticket_body = ticket_context
    # 清除环境变量后也不能读取开发者本机的邮件配置。
    monkeypatch.setitem(smtp.SmtpSettings.model_config, "env_file", None)
    smtp_names = (
        "SMTP_HOST", "SMTP_PORT", "SMTP_SECURITY", "SMTP_USERNAME",
        "SMTP_PASSWORD", "SMTP_FROM", "SMTP_TEST_RECIPIENTS",
    )
    for name in smtp_names:
        monkeypatch.delenv(name, raising=False)
    ticket = (await client.post("/api/tickets", headers=headers, json=ticket_body)).json()
    path = f"/api/tickets/{ticket['id']}/emails"
    response = await client.post(path, headers=headers, json={
        "request_id": str(uuid4()), "recipient": "inbox@example.com", "subject": "处理说明",
        "content": "测试内容", "confirmed": True,
    })
    assert response.status_code == 503, response.text
    assert (await client.get(path, headers=headers)).json() == []
