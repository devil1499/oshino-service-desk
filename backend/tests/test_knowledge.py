import pytest
from test_postgres_foundation import database as database
from test_tickets import ticket_context as ticket_context

from app.modules.knowledge.text import split_text


def test_split_text_keeps_overlap_and_tail():
    text = "".join(chr(0x4E00 + i) for i in range(1001))
    chunks = split_text(text)
    assert [len(chunk) for chunk in chunks] == [500, 500, 161]
    assert chunks[0][-80:] == chunks[1][:80]
    assert chunks[-1].endswith(text[-20:])


def document_body(catalog, **changes):
    return {
        **{key: catalog[key] for key in ("product_id", "module_id", "category_id")},
        "title": "E401 登录处理规范",
        "content": "# 登录规范\n重新绑定角色后验证登录。",
        **changes,
    }


@pytest.mark.postgres
async def test_knowledge_list_searches_title_and_content(ticket_context):
    client, headers, catalog = ticket_context
    for changes in [{}, {"title": "付款说明", "content": "重复扣款需核对流水号。"}]:
        response = await client.post("/api/knowledge", headers=headers, json=document_body(catalog, **changes))
        assert response.status_code == 201, response.text
    result = (await client.get("/api/knowledge?q=E401", headers=headers)).json()
    assert result["total"] == 1
    assert result["items"][0]["title"] == "E401 登录处理规范"
    result = (await client.get("/api/knowledge?q=流水号", headers=headers)).json()
    assert result["total"] == 1
    assert result["items"][0]["title"] == "付款说明"


@pytest.mark.postgres
async def test_admin_upload_edit_publish_disable(ticket_context):
    client, headers, catalog = ticket_context
    metadata = document_body(catalog)
    metadata.pop("content")
    response = await client.post(
        "/api/knowledge/upload",
        headers=headers,
        data=metadata,
        files={"file": ("login.md", "# E401\n重新绑定角色再登录。".encode(), "text/markdown")},
    )
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["status"] == "draft"
    assert document["source_name"] == "login.md"
    path = f"/api/knowledge/{document['id']}"
    published = await client.post(path + "/publish", headers=headers)
    assert published.status_code == 200, published.text
    assert published.json()["chunk_count"] == 1
    assert (await client.post(path + "/publish", headers=headers)).status_code == 409
    updated = await client.put(
        path + "/content",
        headers=headers,
        json=document_body(catalog, title="新版登录规范", content="先检查租户和角色。"),
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "draft"
    assert updated.json()["chunk_count"] == 0
    assert updated.json()["revision"] > published.json()["revision"]
    assert (await client.post(path + "/publish", headers=headers)).status_code == 200
    assert (await client.post(path + "/disable", headers=headers)).json()["status"] == "disabled"
    assert (await client.get(path, headers=headers)).json()["content"] == "先检查租户和角色。"


@pytest.mark.postgres
async def test_staff_can_only_read_published_documents(ticket_context):
    client, headers, catalog = ticket_context
    credentials = {"username": "knowledge_staff", "password": "Only-test-12345", "display_name": "知识客服"}
    assert (await client.post("/api/users", headers=headers, json=credentials)).status_code == 201
    login = await client.post("/api/auth/login", json={key: credentials[key] for key in ("username", "password")})
    staff = {"Authorization": "Bearer " + login.json()["access_token"]}
    body = document_body(catalog)
    document = (await client.post("/api/knowledge", headers=headers, json=body)).json()
    path = f"/api/knowledge/{document['id']}"
    assert (await client.get("/api/knowledge")).status_code == 401
    assert (await client.get("/api/knowledge", headers=staff)).json()["total"] == 0
    assert (await client.get(path, headers=staff)).status_code == 403
    assert (await client.post("/api/knowledge", headers=staff, json=body)).status_code == 403
    assert (await client.put(path + "/content", headers=staff, json=body)).status_code == 403
    assert (await client.post(path + "/publish", headers=staff)).status_code == 403
    assert (await client.post(path + "/disable", headers=staff)).status_code == 403
    assert (await client.post(path + "/publish", headers=headers)).status_code == 200
    assert (await client.get("/api/knowledge", headers=staff)).json()["total"] == 1
    assert (await client.get(path, headers=staff)).json()["content"] == body["content"]
    assert (await client.post(path + "/disable", headers=headers)).status_code == 200
    assert (await client.get(path, headers=staff)).status_code == 403
    assert (await client.get("/api/knowledge", headers=staff)).json()["total"] == 0


@pytest.mark.postgres
@pytest.mark.parametrize(
    ("filename", "content", "status"),
    [
        ("image.png", b"not text", 422),
        ("text.md", b"\xff", 422),
        ("empty.txt", b"", 422),
        ("empty.md", b"   ", 422),
        ("large.txt", b"a" * (256 * 1024 + 1), 413),
    ],
)
async def test_invalid_upload_is_rejected(ticket_context, filename, content, status):
    client, headers, catalog = ticket_context
    metadata = document_body(catalog)
    metadata.pop("content")
    response = await client.post(
        "/api/knowledge/upload", headers=headers, data=metadata, files={"file": (filename, content)}
    )
    assert response.status_code == status, response.text
    assert (await client.get("/api/knowledge", headers=headers)).json()["total"] == 0


@pytest.mark.postgres
@pytest.mark.parametrize(
    "changes",
    [
        {"title": " "},
        {"content": " "},
        {"content": "x" * 100001},
        {"module_id": 999999},
        {"status": "published"},
    ],
)
async def test_document_input_and_catalog_are_validated(ticket_context, changes):
    client, headers, catalog = ticket_context
    response = await client.post("/api/knowledge", headers=headers, json=document_body(catalog, **changes))
    assert response.status_code == 422, response.text
    assert (await client.get("/api/knowledge", headers=headers)).json()["total"] == 0
