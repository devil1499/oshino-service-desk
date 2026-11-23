import csv
import io

import pytest
from test_postgres_foundation import database as database
from test_tickets import ticket_context as ticket_context


def csv_file(rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return {"file": ("tickets.csv", output.getvalue().encode("utf-8-sig"), "text/csv")}


async def import_row(client, headers, catalog):
    names = {}
    for kind, field in [("products", "product"), ("modules", "module"), ("categories", "category")]:
        rows = (await client.get("/api/config/" + kind, headers=headers)).json()
        names[field] = next(row["name"] for row in rows if row["id"] == catalog[field + "_id"])
    return {
        "import_key": "case-001",
        "title": "模拟：登录错误 E401",
        "description": "登录失败，提示 E401\n已核对账号",
        "customer_name": "模拟客户",
        "customer_email": "demo@example.com",
        **names,
        "priority": "P2",
        "status": "resolved",
        "solution": "重新绑定角色后登录成功",
    }


@pytest.mark.postgres
async def test_imported_case_can_be_read(ticket_context):
    client, headers, catalog = ticket_context
    row = await import_row(client, headers, catalog)
    response = await client.post("/api/tickets/import", headers=headers, files=csv_file([row]))
    assert response.status_code == 201, response.text
    assert response.json()["imported"] == 1
    detail = (await client.get(f"/api/tickets/{response.json()['ticket_ids'][0]}", headers=headers)).json()
    assert detail["description"] == row["description"]
    assert detail["solution"] == row["solution"]
    assert detail["status"] == "resolved"
    assert detail["records"][0]["kind"] == "imported"


@pytest.mark.postgres
async def test_import_history_excludes_manual_tickets_and_keeps_pagination_filters(ticket_context):
    client, headers, catalog = ticket_context
    manual = await client.post("/api/tickets", headers=headers, json=catalog)
    assert manual.status_code == 201
    resolved = await import_row(client, headers, catalog)
    pending = {**resolved, "import_key": "case-002", "title": "待处理的历史问题", "status": "pending", "solution": ""}
    imported = await client.post("/api/tickets/import", headers=headers, files=csv_file([resolved, pending]))
    assert imported.status_code == 201
    ids = imported.json()["ticket_ids"]

    first = (await client.get("/api/tickets?imported_only=true&page_size=1", headers=headers)).json()
    assert first["total"] == 2
    assert [item["id"] for item in first["items"]] == [ids[1]]
    second = (await client.get("/api/tickets?imported_only=true&page_size=1&page=2", headers=headers)).json()
    assert second["total"] == 2
    assert [item["id"] for item in second["items"]] == [ids[0]]
    filtered = (await client.get("/api/tickets?imported_only=true&status=resolved", headers=headers)).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == ids[0]
    assert (await client.get("/api/tickets?imported_only=true&keyword=待处理", headers=headers)).json()["total"] == 1
    assert (await client.get("/api/tickets", headers=headers)).json()["total"] == 3


@pytest.mark.postgres
@pytest.mark.parametrize(
    "changes",
    [
        {"solution": ""},
        {"customer_email": "invalid"},
        {"status": "closed"},
        {"status": "pending", "solution": "不应有方案"},
        {"module": "不存在"},
        {"title": " "},
        {"priority": "P5"},
    ],
)
async def test_invalid_row_rejects_entire_batch(ticket_context, changes):
    client, headers, catalog = ticket_context
    first = await import_row(client, headers, catalog)
    second = {**first, "import_key": "case-002", **changes}
    response = await client.post("/api/tickets/import", headers=headers, files=csv_file([first, second]))
    assert response.status_code == 422
    assert "第 2 条" in response.json()["detail"]
    assert (await client.get("/api/tickets", headers=headers)).json()["total"] == 0


@pytest.mark.postgres
async def test_duplicate_keys_and_repeated_upload_are_rejected(ticket_context):
    client, headers, catalog = ticket_context
    row = await import_row(client, headers, catalog)
    assert (await client.post("/api/tickets/import", headers=headers, files=csv_file([row, row]))).status_code == 409
    assert (await client.get("/api/tickets", headers=headers)).json()["total"] == 0
    assert (await client.post("/api/tickets/import", headers=headers, files=csv_file([row]))).status_code == 201
    assert (await client.post("/api/tickets/import", headers=headers, files=csv_file([row]))).status_code == 409
    assert (await client.get("/api/tickets", headers=headers)).json()["total"] == 1


@pytest.mark.postgres
async def test_import_requires_admin(ticket_context):
    client, headers, catalog = ticket_context
    body = {"username": "staff_import", "password": "Only-test-12345", "display_name": "测试客服"}
    assert (await client.post("/api/users", headers=headers, json=body)).status_code == 201
    login = await client.post("/api/auth/login", json={"username": body["username"], "password": body["password"]})
    staff = {"Authorization": "Bearer " + login.json()["access_token"]}
    file = csv_file([await import_row(client, headers, catalog)])
    assert (await client.post("/api/tickets/import", files=file)).status_code == 401
    assert (await client.post("/api/tickets/import", headers=staff, files=file)).status_code == 403


@pytest.mark.postgres
@pytest.mark.parametrize(
    "content,status",
    [
        (b"wrong,header\na,b\n", 422),
        (b"\xff\xfe", 422),
        (b"x" * (4 * 1024 * 1024 + 1), 413),
        (b"", 422),
    ],
)
async def test_invalid_upload_format(ticket_context, content, status):
    client, headers, _ = ticket_context
    response = await client.post("/api/tickets/import", headers=headers, files={"file": ("x.csv", content)})
    assert response.status_code == status


@pytest.mark.postgres
async def test_disabled_config_and_row_limit(ticket_context):
    client, headers, catalog = ticket_context
    row = await import_row(client, headers, catalog)
    too_many = [{**row, "import_key": f"large-{number}"} for number in range(5001)]
    response = await client.post("/api/tickets/import", headers=headers, files=csv_file(too_many))
    assert response.status_code == 422
    assert "5000" in response.json()["detail"]
    updated = await client.put(
        f"/api/config/products/{catalog['product_id']}",
        headers=headers,
        json={"name": row["product"], "is_active": False},
    )
    assert updated.status_code == 200
    rejected = await client.post("/api/tickets/import", headers=headers, files=csv_file([row]))
    assert rejected.status_code == 422
    assert "启用" in rejected.json()["detail"]
    assert (await client.get("/api/tickets", headers=headers)).json()["total"] == 0


@pytest.mark.postgres
async def test_concurrent_import_and_manual_ticket_remain_valid(ticket_context):
    import asyncio

    client, headers, catalog = ticket_context
    row = await import_row(client, headers, catalog)
    responses = await asyncio.gather(
        *[client.post("/api/tickets/import", headers=headers, files=csv_file([row])) for _ in range(2)]
    )
    assert sorted(response.status_code for response in responses) == [201, 409]
    for _ in range(2):
        assert (await client.post("/api/tickets", headers=headers, json=catalog)).status_code == 201
    pending = {**row, "import_key": "pending-001", "status": "pending", "solution": ""}
    assert (await client.post("/api/tickets/import", headers=headers, files=csv_file([pending]))).status_code == 201
    assert (await client.get("/api/tickets", headers=headers)).json()["total"] == 4
