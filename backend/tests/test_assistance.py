import json

import httpx2
import pytest
from test_import import csv_file, import_row
from test_knowledge import document_body
from test_knowledge_search import build_index as build_knowledge
from test_knowledge_search import create_query
from test_postgres_foundation import database as database
from test_similar import build_index as build_cases
from test_similar import retrieval as retrieval

from app.integrations.chat import ChatClient
from app.modules.analysis.assistance import get_chat_client

pytestmark = pytest.mark.postgres


@pytest.fixture
async def assistance(retrieval):
    app, client, headers, catalog, config = retrieval
    row = await import_row(client, headers, catalog)
    ids = (await client.post("/api/tickets/import", headers=headers, files=csv_file([row]))).json()["ticket_ids"]
    await build_cases(app, config, ids)
    document = (await client.post("/api/knowledge", headers=headers, json=document_body(catalog))).json()
    await client.post(f"/api/knowledge/{document['id']}/publish", headers=headers)
    await build_knowledge(app, config)
    ticket_id = await create_query(client, headers, catalog)
    behavior = {"invalid_source": False, "calls": 0}

    def chat():
        def respond(request):
            behavior["calls"] += 1
            body = json.loads(request.content)
            data = json.loads(body["messages"][1]["content"])
            source = data["sources"][0]["source_id"]
            if "categories" not in data:
                answer = {"source_ids": [source]}
            else:
                answer = dict(
                    summary="登录失败",
                    diagnosis="需核查角色绑定",
                    category_id=catalog["category_id"],
                    priority="P2",
                    reason="登录功能受阻",
                    steps=[
                        {
                            "instruction": "检查角色绑定后验证登录",
                            "source_ids": ["T999999"] if behavior["invalid_source"] else [source],
                        }
                    ],
                    risks=[],
                    confirmations=["需核实账号状态"],
                    reply_subject="登录问题处理建议",
                    reply_body="请核实角色绑定，处理前请确认账号权限。",
                )
            return httpx2.Response(
                200,
                json={
                    "id": "test",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "fixture",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)},
                        }
                    ],
                },
            )

        with ChatClient(
            "https://model.example/v1", "test-only", "fixture", httpx2.Client(transport=httpx2.MockTransport(respond))
        ) as model:
            yield model

    app.dependency_overrides[get_chat_client] = chat
    return client, headers, ticket_id, behavior


async def test_generate_review_adopt_and_history(assistance):
    client, headers, ticket_id, behavior = assistance
    path = f"/api/tickets/{ticket_id}"
    response = await client.post(path + "/assist", headers=headers)
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["sources"] and run["draft"]["steps"]
    assert behavior["calls"] == 2
    assert len((await client.get(path + "/assistance", headers=headers)).json()) == 1
    adoption = path + f"/assistance/{run['id']}/adopt"
    body = dict(confirmed=True, solution="人工核查角色绑定", reply="已记录建议，请核查后再操作。")
    assert (await client.post(adoption, headers=headers, json={**body, "confirmed": False})).status_code == 422
    assert (await client.post(adoption, headers=headers, json=body)).status_code == 200
    assert (await client.post(adoption, headers=headers, json=body)).status_code == 409
    ticket = (await client.get(path, headers=headers)).json()
    assert ticket["status"] == "pending"
    assert ticket["records"][-1]["kind"] == "ai_adopted"
    assert (await client.post(path + "/assist")).status_code == 401


async def test_invalid_citation_does_not_save_a_success(assistance):
    client, headers, ticket_id, behavior = assistance
    behavior["invalid_source"] = True
    path = f"/api/tickets/{ticket_id}"
    assert (await client.post(path + "/assist", headers=headers)).status_code == 502
    assert (await client.get(path + "/assistance", headers=headers)).json() == []


async def test_changed_ticket_cannot_adopt_old_advice(assistance):
    client, headers, ticket_id, _ = assistance
    path = f"/api/tickets/{ticket_id}"
    run = (await client.post(path + "/assist", headers=headers)).json()
    await client.patch(path, headers=headers, json={"title": "另一种登录故障"})
    response = await client.post(
        path + f"/assistance/{run['id']}/adopt",
        headers=headers,
        json=dict(confirmed=True, solution="检查", reply="检查"),
    )
    assert response.status_code == 409


async def test_changed_source_and_closed_ticket_reject_advice(assistance):
    client, headers, ticket_id, behavior = assistance
    path = f"/api/tickets/{ticket_id}"
    run = (await client.post(path + "/assist", headers=headers)).json()
    source = run["sources"][0]
    assert source["kind"] == "ticket"
    await client.patch(f"/api/tickets/{source['entity_id']}", headers=headers, json={"title": "参考依据更新"})
    adoption = path + f"/assistance/{run['id']}/adopt"
    assert (
        await client.post(adoption, headers=headers, json=dict(confirmed=True, solution="核查", reply="核查"))
    ).status_code == 409
    assert (await client.post(path + "/start", headers=headers)).status_code == 200
    assert (await client.post(path + "/resolve", headers=headers, json={"solution": "已核查"})).status_code == 200
    assert (
        await client.post(path + "/close", headers=headers, json={"customer_reply_confirmed": True})
    ).status_code == 200
    before = behavior["calls"]
    assert (await client.post(path + "/assist", headers=headers)).status_code == 409
    assert (
        await client.post(adoption, headers=headers, json=dict(confirmed=True, solution="核查", reply="核查"))
    ).status_code == 409
    assert behavior["calls"] == before
