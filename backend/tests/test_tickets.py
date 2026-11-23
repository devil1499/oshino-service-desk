import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from test_foundation import make_test_settings
from test_postgres_foundation import admin_headers, app_client
from test_postgres_foundation import database as database

from app.main import create_app


async def test_ticket_routes_require_login():
    app = create_app(make_test_settings(), recover_jobs=False)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get("/api/tickets")
        assert response.status_code == 401


@pytest.fixture
async def ticket_context(database):
    async with app_client(database) as client:
        headers = await admin_headers(client, database)
        product = await client.post("/api/config/products", headers=headers, json={"name": "工单测试产品"})
        assert product.status_code == 201
        module = await client.post(
            "/api/config/modules", headers=headers, json={"name": "账号模块", "product_id": product.json()["id"]}
        )
        assert module.status_code == 201
        categories = (await client.get("/api/config/categories", headers=headers)).json()
        body = {
            "title": "无法登录",
            "description": "输入账号后提示登录失败",
            "customer_name": "测试客户",
            "customer_email": "customer@example.com",
            "priority": "P2",
            "product_id": product.json()["id"],
            "module_id": module.json()["id"],
            "category_id": categories[0]["id"],
        }
        yield client, headers, body


@pytest.mark.postgres
async def test_ticket_can_be_created_read_and_persisted(ticket_context, database):
    client, headers, body = ticket_context
    created = await client.post("/api/tickets", headers=headers, json=body)
    assert created.status_code == 201, created.text
    ticket = created.json()
    assert ticket["status"] == "pending"
    assert len(ticket["records"]) == 1
    async with app_client(database) as restarted:
        detail = await restarted.get(f"/api/tickets/{ticket['id']}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["title"] == body["title"]
        assert detail.json()["records"] == ticket["records"]


@pytest.mark.postgres
async def test_workflow_records_and_closed_read_only(ticket_context):
    client, headers, body = ticket_context
    created = await client.post("/api/tickets", headers=headers, json=body)
    path = f"/api/tickets/{created.json()['id']}"
    assert (await client.post(path + "/resolve", headers=headers, json={"solution": "解决"})).status_code == 409
    assert (
        await client.post(path + "/close", headers=headers, json={"customer_reply_confirmed": True})
    ).status_code == 409
    responses = await asyncio.gather(*(client.post(path + "/start", headers=headers) for _ in range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert (await client.post(path + "/records", headers=headers, json={"content": "核对激活状态"})).status_code == 201
    assert (await client.patch(path, headers=headers, json={"title": "登录故障已核实"})).status_code == 200
    assert (await client.post(path + "/resolve", headers=headers, json={"solution": "  "})).status_code == 422
    resolved = await client.post(path + "/resolve", headers=headers, json={"solution": "激活账号后恢复登录"})
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert (
        await client.post(path + "/close", headers=headers, json={"customer_reply_confirmed": False})
    ).status_code == 422
    closed = await client.post(path + "/close", headers=headers, json={"customer_reply_confirmed": True})
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert (await client.patch(path, headers=headers, json={"title": "不允许"})).status_code == 409
    assert (await client.post(path + "/records", headers=headers, json={"content": "不允许"})).status_code == 409
    detail = (await client.get(path, headers=headers)).json()
    assert detail["solution"] == "激活账号后恢复登录"
    assert sum(record["kind"] == "status" for record in detail["records"]) == 3
    assert any(record["content"] == "核对激活状态" for record in detail["records"])


@pytest.mark.postgres
async def test_ticket_validation_filters_and_disabled_catalog(ticket_context):
    client, headers, body = ticket_context
    created = await client.post("/api/tickets", headers=headers, json=body)
    ticket = created.json()
    path = f"/api/tickets/{ticket['id']}"
    for changes in [
        {"title": None},
        {"title": " "},
        {"status": "closed"},
        {"priority": "P0"},
        {"customer_email": "invalid"},
        {"owner_id": 2147483647},
        {},
    ]:
        assert (await client.patch(path, headers=headers, json=changes)).status_code == 422
    other = await client.post("/api/config/products", headers=headers, json={"name": "其他产品"})
    assert (await client.patch(path, headers=headers, json={"product_id": other.json()["id"]})).status_code == 422
    assert (await client.get(path, headers=headers)).json()["product_id"] == body["product_id"]
    category_id = body["category_id"]
    assert (
        await client.put(
            f"/api/config/categories/{category_id}", headers=headers, json={"name": "停用分类", "is_active": False}
        )
    ).status_code == 200
    assert (await client.patch(path, headers=headers, json={"title": "补充问题"})).status_code == 200
    assert (await client.post("/api/tickets", headers=headers, json=body)).status_code == 422
    result = await client.get(
        "/api/tickets",
        headers=headers,
        params={
            "keyword": "补充",
            "status": "pending",
            "priority": "P2",
            "product_id": body["product_id"],
            "module_id": body["module_id"],
            "category_id": category_id,
            "owner_id": ticket["owner_id"],
            "page_size": 1,
        },
    )
    assert result.status_code == 200
    assert result.json()["total"] == 1
    assert result.json()["items"][0]["id"] == ticket["id"]
    assert (await client.get("/api/tickets?page=2&page_size=1", headers=headers)).json()["items"] == []
    assert (await client.get("/api/tickets?page=0", headers=headers)).status_code == 422
    assert (await client.get("/api/tickets?page_size=101", headers=headers)).status_code == 422
    assert (await client.get("/api/tickets/2147483647", headers=headers)).status_code == 404


@pytest.mark.postgres
async def test_staff_can_work_and_disabled_staff_cannot(ticket_context):
    client, headers, body = ticket_context
    staff = await client.post(
        "/api/users", headers=headers, json={"username": "agent", "display_name": "客服", "password": "Test-only-8392"}
    )
    assert staff.status_code == 201
    login = await client.post("/api/auth/login", json={"username": "agent", "password": "Test-only-8392"})
    staff_headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    ticket = await client.post("/api/tickets", headers=staff_headers, json=body)
    assert ticket.status_code == 201
    assert ticket.json()["owner_id"] == staff.json()["id"]
    path = f"/api/tickets/{ticket.json()['id']}"
    assert (await client.post(path + "/start", headers=staff_headers)).status_code == 200
    assert (await client.patch(path, headers=headers, json={"owner_id": staff.json()["id"]})).status_code == 200
    assert (
        await client.patch(f"/api/users/{staff.json()['id']}", headers=headers, json={"is_active": False})
    ).status_code == 200
    assert (await client.get(path, headers=staff_headers)).status_code == 401
