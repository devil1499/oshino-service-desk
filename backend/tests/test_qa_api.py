import asyncio
import threading
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy.engine import make_url
from test_knowledge import document_body
from test_knowledge_search import build_index
from test_postgres_foundation import TEST_PASSWORD
from test_postgres_foundation import database as database
from test_similar import retrieval as retrieval

from app.integrations.chat import ChatError
from app.modules.analysis.router import get_retrieval_settings
from app.modules.qa.router import get_chat_client

pytestmark = pytest.mark.postgres


@pytest.fixture
async def qa(retrieval):
    app, client, headers, catalog, config = retrieval
    document = (await client.post("/api/knowledge", headers=headers, json=document_body(catalog))).json()
    assert (await client.post(f"/api/knowledge/{document['id']}/publish", headers=headers)).status_code == 200
    await build_index(app, config)
    calls = []

    class Model:
        model = "test-model"

        def ask(self, instruction, data, result_type):
            calls.append(result_type.__name__)
            if result_type.__name__ == "Plan":
                return result_type(action="search", text="登录 E401 角色绑定")
            return result_type(action="answer", text="有依据", paragraphs=[{
                "text": "请检查角色绑定。", "source_ids": [data["sources"][0]["source_id"]],
            }])

    app.dependency_overrides[get_chat_client] = lambda: Model()
    return app, client, headers, catalog, document, calls


async def test_answer_is_saved_with_sources_and_idempotent(qa):
    app, client, headers, catalog, document, calls = qa
    created = await client.post(
        "/api/qa/conversations", headers=headers,
        json={"product_id": catalog["product_id"], "title": "登录问题"},
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]
    request_id = str(uuid4())
    path = f"/api/qa/conversations/{conversation_id}/messages"
    sent = await client.post(path, headers=headers, json={"request_id": request_id, "text": "E401 怎么处理？"})
    assert sent.status_code == 201, sent.text
    answer = sent.json()
    assert answer["status"] == "answered"
    assert answer["sources"][0]["document_id"] == document["id"]
    assert "K" in answer["content"]
    assert answer['has_run'] is True
    assert answer['duration_ms'] >= 0
    assert answer['token_usage']['calls'] == 2
    assert answer['token_usage']['total_tokens'] is None  # 测试模型不提供 usage。
    run = (await client.get(f"{path}/{answer['id']}/run", headers=headers)).json()
    assert run['status'] == 'answered'
    assert [step['name'] for step in run['steps']] == ['plan', 'retrieve', 'assess', 'verify_sources']
    assert run['sources'][0]['document_id'] == document['id']
    assert run['question']['text'] == 'E401 怎么处理？'
    repeated = await client.post(path, headers=headers, json={"request_id": request_id, "text": "E401 怎么处理？"})
    assert repeated.json() == answer
    assert len(calls) == 2
    conflict = await client.post(path, headers=headers, json={"request_id": request_id, "text": "另一个问题"})
    assert conflict.status_code == 409
    messages = (await client.get(path, headers=headers)).json()
    assert [item["role"] for item in messages["items"]] == ["user", "assistant"]
    assert (await client.get("/api/qa/conversations", headers=headers)).json()["items"][0]["id"] == conversation_id


async def test_other_user_cannot_read_or_send_to_conversation(qa):
    app, client, headers, catalog, document, calls = qa
    created = await client.post(
        "/api/qa/conversations", headers=headers,
        json={"product_id": catalog["product_id"], "title": "私人会话"},
    )
    conversation_id = created.json()["id"]
    response = await client.post(
        "/api/users", headers=headers,
        json={"username": "qa_staff", "display_name": "客服", "password": TEST_PASSWORD},
    )
    assert response.status_code == 201, response.text
    login = await client.post("/api/auth/login", json={"username": "qa_staff", "password": TEST_PASSWORD})
    staff = {"Authorization": "Bearer " + login.json()["access_token"]}
    path = f"/api/qa/conversations/{conversation_id}/messages"
    assert (await client.get("/api/qa/conversations", headers=staff)).json()["items"] == []
    assert (await client.get(path, headers=staff)).status_code == 404
    assert (await client.get(f"{path}/1/run", headers=staff)).status_code == 404
    forbidden = await client.post(path, headers=staff, json={"request_id": str(uuid4()), "text": "查看"})
    assert forbidden.status_code == 404


async def test_model_failure_is_visible_and_next_question_can_run(qa):
    app, client, headers, catalog, document, calls = qa
    working_model = app.dependency_overrides[get_chat_client]

    class BrokenModel:
        model = "broken-model"

        def ask(self, instruction, data, result_type):
            raise ChatError("无法连接聊天模型，请检查地址与网络")

    app.dependency_overrides[get_chat_client] = lambda: BrokenModel()
    conversation = (await client.post(
        "/api/qa/conversations", headers=headers,
        json={"product_id": catalog["product_id"], "title": "失败恢复"},
    )).json()
    path = f"/api/qa/conversations/{conversation['id']}/messages"
    failed = await client.post(path, headers=headers, json={"request_id": str(uuid4()), "text": "E401"})
    assert failed.status_code == 502
    assert "无法连接聊天模型" in failed.json()["detail"]
    history = (await client.get(path, headers=headers)).json()["items"]
    assert history[-1]["status"] == "failed"
    assert history[-1]["error_code"] == "HTTP_502"
    assert history[-1]['duration_ms'] >= 0
    run = (await client.get(f"{path}/{history[-1]['id']}/run", headers=headers)).json()
    assert run['status'] == 'failed'
    assert run['steps'][0]['status'] == 'failed'
    assert run['usage']['chat']['total_tokens'] is None
    app.dependency_overrides[get_chat_client] = working_model
    retry = await client.post(path, headers=headers, json={"request_id": str(uuid4()), "text": "E401 角色绑定"})
    assert retry.status_code == 201, retry.text
    assert retry.json()["status"] == "answered"


async def test_search_stays_within_selected_product(qa):
    app, client, headers, catalog, document, calls = qa
    other_product = (await client.post(
        "/api/config/products", headers=headers, json={"name": "另一个产品"},
    )).json()
    other_module = (await client.post(
        "/api/config/modules", headers=headers,
        json={"name": "账号模块", "product_id": other_product["id"]},
    )).json()
    other_body = document_body(catalog)
    other_body.update(product_id=other_product["id"], module_id=other_module["id"])
    other_document = (await client.post("/api/knowledge", headers=headers, json=other_body)).json()
    assert (await client.post(f"/api/knowledge/{other_document['id']}/publish", headers=headers)).status_code == 200
    # fixture 的知识索引在当前专用测试目录，新增文档后从数据库完整重建。
    retrieval_settings = app.dependency_overrides[get_retrieval_settings]()
    await build_index(app, retrieval_settings)
    conversation = (await client.post(
        "/api/qa/conversations", headers=headers,
        json={"product_id": catalog["product_id"], "title": "产品范围"},
    )).json()
    sent = await client.post(
        f"/api/qa/conversations/{conversation['id']}/messages", headers=headers,
        json={"request_id": str(uuid4()), "text": "E401 怎么处理？"},
    )
    assert sent.status_code == 201, sent.text
    assert {source["document_id"] for source in sent.json()["sources"]} == {document["id"]}


async def test_one_conversation_allows_only_one_running_answer(qa):
    app, client, headers, catalog, document, calls = qa
    started = threading.Event()
    release = threading.Event()
    working_model = app.dependency_overrides[get_chat_client]
    delegate = working_model()

    class SlowModel:
        model = "slow-model"

        def ask(self, instruction, data, result_type):
            if result_type.__name__ == "Plan":
                started.set()
                release.wait(timeout=15)
            return delegate.ask(instruction, data, result_type)

    app.dependency_overrides[get_chat_client] = lambda: SlowModel()
    conversation = (await client.post(
        "/api/qa/conversations", headers=headers,
        json={"product_id": catalog["product_id"], "title": "并发测试"},
    )).json()
    path = f"/api/qa/conversations/{conversation['id']}/messages"
    first = asyncio.create_task(client.post(path, headers=headers, json={"request_id": str(uuid4()), "text": "E401"}))
    try:
        assert await asyncio.to_thread(started.wait, 10)
        second = await client.post(path, headers=headers, json={"request_id": str(uuid4()), "text": "另一个问题"})
        assert second.status_code == 409
    finally:
        release.set()
    assert (await first).status_code == 201


async def test_source_disabled_during_generation_fails_without_stuck_session(qa):
    app, client, headers, catalog, document, calls = qa
    working_model = app.dependency_overrides[get_chat_client]
    delegate = working_model()
    url = make_url(app.state.settings.database_url.get_secret_value()).set(drivername="postgresql")

    class ChangingModel:
        model = "changing-model"

        def ask(self, instruction, data, result_type):
            if result_type.__name__ == "Assessment":
                with psycopg.connect(url.render_as_string(hide_password=False)) as connection:
                    connection.execute(
                        "UPDATE knowledge_documents SET status = 'disabled' WHERE id = %s", (document["id"],)
                    )
            return delegate.ask(instruction, data, result_type)

    app.dependency_overrides[get_chat_client] = lambda: ChangingModel()
    conversation = (await client.post(
        "/api/qa/conversations", headers=headers,
        json={"product_id": catalog["product_id"], "title": "引用版本"},
    )).json()
    path = f"/api/qa/conversations/{conversation['id']}/messages"
    failed = await client.post(path, headers=headers, json={"request_id": str(uuid4()), "text": "E401"})
    assert failed.status_code == 409, failed.text
    assert (await client.get(path, headers=headers)).json()["items"][-1]["status"] == "failed"
    app.dependency_overrides[get_chat_client] = working_model
    assert (await client.post(f"/api/knowledge/{document['id']}/publish", headers=headers)).status_code == 200
    retrieval_settings = app.dependency_overrides[get_retrieval_settings]()
    await build_index(app, retrieval_settings)
    retry = await client.post(path, headers=headers, json={"request_id": str(uuid4()), "text": "E401 角色绑定"})
    assert retry.status_code == 201, retry.text


async def test_outdated_knowledge_index_is_reported_as_index_error(qa):
    app, client, headers, catalog, document, calls = qa
    assert (await client.post(f"/api/knowledge/{document['id']}/disable", headers=headers)).status_code == 200
    conversation = (await client.post(
        "/api/qa/conversations", headers=headers,
        json={"product_id": catalog["product_id"], "title": "索引过期"},
    )).json()
    path = f"/api/qa/conversations/{conversation['id']}/messages"
    response = await client.post(path, headers=headers, json={"request_id": str(uuid4()), "text": "E401"})
    assert response.status_code == 503
    assert "重建知识索引" in response.json()["detail"]
    assert (await client.get(path, headers=headers)).json()["items"][-1]["status"] == "failed"


async def test_published_document_after_empty_index_requires_rebuild(qa):
    app, client, headers, catalog, document, calls = qa
    assert (await client.post(f"/api/knowledge/{document['id']}/disable", headers=headers)).status_code == 200
    retrieval_settings = app.dependency_overrides[get_retrieval_settings]()
    await build_index(app, retrieval_settings)
    assert (await client.post(f"/api/knowledge/{document['id']}/publish", headers=headers)).status_code == 200
    conversation = (await client.post(
        "/api/qa/conversations", headers=headers,
        json={"product_id": catalog["product_id"], "title": "空索引后发布"},
    )).json()
    response = await client.post(
        f"/api/qa/conversations/{conversation['id']}/messages", headers=headers,
        json={"request_id": str(uuid4()), "text": "E401"},
    )
    assert response.status_code == 503
    assert "重建知识索引" in response.json()["detail"]


async def test_restart_keeps_partial_trace_without_fabricating_total_duration(qa):
    from app.modules.qa.service import interrupt_questions

    app, client, headers, catalog, document, calls = qa
    started = threading.Event()
    release = threading.Event()
    delegate = app.dependency_overrides[get_chat_client]()

    class WaitingModel:
        model = 'waiting-model'

        def ask(self, instruction, data, result_type):
            if result_type.__name__ == 'Plan':
                started.set()
                release.wait(timeout=15)
            return delegate.ask(instruction, data, result_type)

    app.dependency_overrides[get_chat_client] = lambda: WaitingModel()
    conversation = (await client.post('/api/qa/conversations', headers=headers,
                                     json={'product_id': catalog['product_id'], 'title': '重启恢复'})).json()
    path = f"/api/qa/conversations/{conversation['id']}/messages"
    task = asyncio.create_task(client.post(path, headers=headers, json={'request_id': str(uuid4()), 'text': 'E401'}))
    try:
        assert await asyncio.to_thread(started.wait, 10)
        await interrupt_questions(app.state.session_factory)
    finally:
        release.set()
    assert (await task).status_code == 409
    message = (await client.get(path, headers=headers)).json()['items'][-1]
    assert message['error_code'] == 'INTERRUPTED'
    assert message['duration_ms'] is None
    assert message['token_usage']['complete'] is False
    trace = (await client.get(f"{path}/{message['id']}/run", headers=headers)).json()
    assert trace['duration_ms'] is None
    assert trace['calls'][0]['duration_ms'] is None
    assert trace['steps'][0]['status'] == 'failed'
