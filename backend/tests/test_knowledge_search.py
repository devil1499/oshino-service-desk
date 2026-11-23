import asyncio

import pytest
from sqlalchemy import select
from test_knowledge import document_body
from test_postgres_foundation import database as database
from test_similar import retrieval as retrieval

from app.integrations.knowledge_index import KnowledgeIndex
from app.models import KnowledgeChunk, KnowledgeDocument

pytestmark = pytest.mark.postgres


async def build_index(app, config):
    async with app.state.session_factory() as db:
        records = (
            await db.execute(
                select(KnowledgeChunk, KnowledgeDocument)
                .join(KnowledgeDocument)
                .where(KnowledgeDocument.status == "published")
            )
        ).all()
        rows = [
            {
                "chunk_id": chunk.id,
                "content": document.title + "\n" + chunk.content,
                "dense_vector": [1.0, 0.0, 0.0, 0.0],
                "product_id": document.product_id,
                "module_id": document.module_id,
                "category_id": document.category_id,
                "fingerprint": chunk.fingerprint,
            }
            for chunk, document in records
        ]

    def build():
        with KnowledgeIndex(config.milvus_db_path, config.embedding_model, str(config.model_base_url), 4) as index:
            index.reset()
            if rows:
                index.add(rows)
            index.finish(len(rows))

    await asyncio.to_thread(build)


async def create_query(client, headers, catalog):
    response = await client.post(
        "/api/tickets",
        headers=headers,
        json={
            **catalog,
            "title": "E401 登录失败",
            "description": "角色绑定异常，无法登录。",
            "customer_name": "测试客户",
            "customer_email": "knowledge@example.com",
            "priority": "P2",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_retrieval_checks_publication_and_current_revision(retrieval):
    app, client, headers, catalog, config = retrieval
    document = (await client.post("/api/knowledge", headers=headers, json=document_body(catalog))).json()
    path = f"/api/knowledge/{document['id']}"
    assert (await client.post(path + "/publish", headers=headers)).status_code == 200
    ticket_id = await create_query(client, headers, catalog)
    query = f"/api/tickets/{ticket_id}/knowledge"
    await build_index(app, config)
    response = await client.post(query, headers=headers)
    assert response.status_code == 200, response.text
    hit = response.json()["items"][0]
    assert hit["document_id"] == document["id"]
    assert hit["source_name"] == "手工录入"
    assert hit["chunk_order"] == 1
    assert hit["content"] == document["content"]
    assert (await client.post(query)).status_code == 401
    assert (await client.post(path + "/disable", headers=headers)).status_code == 200
    result = (await client.post(query, headers=headers)).json()
    assert result["items"] == []
    assert result["stale_count"] == 1
    assert (
        await client.put(
            path + "/content", headers=headers, json=document_body(catalog, content="新版：检查租户与账号角色。")
        )
    ).status_code == 200
    assert (await client.post(path + "/publish", headers=headers)).status_code == 200
    assert (await client.post(query, headers=headers)).json()["items"] == []
    await build_index(app, config)
    result = (await client.post(query, headers=headers)).json()
    assert result["items"][0]["content"] == "新版：检查租户与账号角色。"
    assert result["items"][0]["chunk_id"] != hit["chunk_id"]


@pytest.mark.parametrize("same_module", [True, False])
async def test_search_limits_five_chunks_and_expands_category(retrieval, same_module):
    app, client, headers, catalog, config = retrieval
    body = document_body(catalog, content="E401 登录错误需要重新绑定角色。" * 160)
    if not same_module:
        module = (
            await client.post(
                "/api/config/modules", headers=headers, json={"name": "其他模块", "product_id": catalog["product_id"]}
            )
        ).json()
        body["module_id"] = module["id"]
    document = (await client.post("/api/knowledge", headers=headers, json=body)).json()
    assert (await client.post(f"/api/knowledge/{document['id']}/publish", headers=headers)).status_code == 200
    await build_index(app, config)
    ticket_id = await create_query(client, headers, catalog)
    response = await client.post(f"/api/tickets/{ticket_id}/knowledge", headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["items"]) == 5
    assert len({item["chunk_id"] for item in result["items"]}) == 5
    assert result["expanded"] is (not same_module)
    assert all(item["scope"] == ("module" if same_module else "category") for item in result["items"])


async def test_missing_knowledge_index_is_not_success(retrieval):
    app, client, headers, catalog, config = retrieval
    ticket_id = await create_query(client, headers, catalog)
    response = await client.post(f"/api/tickets/{ticket_id}/knowledge", headers=headers)
    assert response.status_code == 503
    assert "索引" in response.json()["detail"]
    assert (await client.post("/api/tickets/999999/knowledge", headers=headers)).status_code == 404
