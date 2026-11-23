import asyncio

import httpx
import httpx2
import pytest
from sqlalchemy import select
from test_import import csv_file, import_row
from test_postgres_foundation import admin_headers
from test_postgres_foundation import database as database

from app.core.retrieval_settings import RetrievalSettings
from app.integrations.case_index import CaseIndex
from app.integrations.embeddings import EmbeddingClient
from app.main import create_app
from app.models import Ticket
from app.modules.analysis.cases import case_row
from app.modules.analysis.router import get_embedding_client, get_retrieval_settings

pytestmark = pytest.mark.postgres


@pytest.fixture
async def retrieval(database, tmp_path):
    config = RetrievalSettings.model_validate(
        dict(
            milvus_db_path=tmp_path / "cases.db",
            model_base_url="https://model.example/v1",
            model_api_key="test-only",
            embedding_model="fixture-model",
            embedding_dimensions=4,
        )
    )
    app = create_app(database)

    def model():
        def reply(request):
            return httpx2.Response(
                200,
                json={
                    "object": "list",
                    "model": "fixture-model",
                    "data": [{"object": "embedding", "index": 0, "embedding": [1.0, 0.0, 0.0, 0.0]}],
                    "usage": {"prompt_tokens": 1, "total_tokens": 1},
                },
            )

        with EmbeddingClient(
            str(config.model_base_url),
            "test-only",
            config.embedding_model,
            4,
            http_client=httpx2.Client(transport=httpx2.MockTransport(reply)),
        ) as client:
            yield client

    app.dependency_overrides[get_retrieval_settings] = lambda: config
    app.dependency_overrides[get_embedding_client] = model
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        headers = await admin_headers(client, database)
        product = (await client.post("/api/config/products", headers=headers, json={"name": "检索产品"})).json()
        module = (
            await client.post(
                "/api/config/modules", headers=headers, json={"name": "账号模块", "product_id": product["id"]}
            )
        ).json()
        categories = (await client.get("/api/config/categories", headers=headers)).json()
        catalog = dict(product_id=product["id"], module_id=module["id"], category_id=categories[0]["id"])
        yield app, client, headers, catalog, config


async def build_index(app, config, ids):
    async with app.state.session_factory() as db:
        tickets = (await db.scalars(select(Ticket).where(Ticket.id.in_(ids)))).all()
        rows = [case_row(ticket, [1.0, 0.0, 0.0, 0.0]) for ticket in tickets]

    def build():
        with CaseIndex(config.milvus_db_path, config.embedding_model, str(config.model_base_url), 4) as index:
            index.reset()
            if rows:
                index.add(rows)
            index.finish(len(rows))

    await asyncio.to_thread(build)


async def test_similarity_excludes_self_unresolved_and_changed_cases(retrieval):
    app, client, headers, catalog, config = retrieval
    row = await import_row(client, headers, catalog)
    rows = [{**row, "import_key": f"case-{i}"} for i in range(4)]
    rows[2].update(status="pending", solution="")
    rows[3].update(status="pending", solution="")
    ids = (await client.post("/api/tickets/import", headers=headers, files=csv_file(rows))).json()["ticket_ids"]
    await build_index(app, config, ids)
    path = f"/api/tickets/{ids[2]}/similar"
    response = await client.post(path, headers=headers)
    assert response.status_code == 200, response.text
    assert {item["id"] for item in response.json()["items"]} == set(ids[:2])
    assert response.json()["expanded"] is True
    assert (
        await client.patch(f"/api/tickets/{ids[0]}", headers=headers, json={"title": "已修改的问题"})
    ).status_code == 200
    result = (await client.post(path, headers=headers)).json()
    assert [item["id"] for item in result["items"]] == [ids[1]]
    assert result["stale_count"] == 2
    assert (await client.post(path)).status_code == 401


@pytest.mark.parametrize("count", [1, 8])
async def test_category_expansion_and_five_result_limit(retrieval, count):
    app, client, headers, catalog, config = retrieval
    row = await import_row(client, headers, catalog)
    query = {**row, "import_key": "query", "status": "pending", "solution": ""}
    references = [{**row, "import_key": f"reference-{i}"} for i in range(count)]
    if count == 1:
        other = (
            await client.post(
                "/api/config/modules", headers=headers, json={"name": "其他模块", "product_id": catalog["product_id"]}
            )
        ).json()
        references[0]["module"] = other["name"]
    ids = (await client.post("/api/tickets/import", headers=headers, files=csv_file([query, *references]))).json()[
        "ticket_ids"
    ]
    await build_index(app, config, ids[1:])
    response = await client.post(f"/api/tickets/{ids[0]}/similar", headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["items"]) == min(count, 5)
    assert result["expanded"] is (count == 1)
    assert all(item["scope"] == ("category" if count == 1 else "module") for item in result["items"])
    assert ids[0] not in {item["id"] for item in result["items"]}
    # 两个客服同时查询时，不能因其中一个请求关闭连接而破坏另一个请求。
    responses = await asyncio.gather(
        *(client.post(f"/api/tickets/{ids[0]}/similar", headers=headers) for _ in range(3))
    )
    assert all(response.status_code == 200 for response in responses)


async def test_missing_index_configuration_and_upstream_failure_are_errors(retrieval):
    app, client, headers, catalog, config = retrieval
    row = await import_row(client, headers, catalog)
    ids = (await client.post("/api/tickets/import", headers=headers, files=csv_file([row]))).json()["ticket_ids"]
    path = f"/api/tickets/{ids[0]}/similar"
    response = await client.post(path, headers=headers)
    assert response.status_code == 503
    assert "索引" in response.json()["detail"]
    await build_index(app, config, ids)

    def failed_model():
        with EmbeddingClient(
            str(config.model_base_url),
            "test-only",
            config.embedding_model,
            4,
            http_client=httpx2.Client(
                transport=httpx2.MockTransport(
                    lambda request: httpx2.Response(429, json={"error": {"message": "private upstream content"}})
                )
            ),
        ) as model:
            yield model

    app.dependency_overrides[get_embedding_client] = failed_model
    response = await client.post(path, headers=headers)
    assert response.status_code == 502
    assert "429" in response.json()["detail"]
    assert "private upstream content" not in response.text
    assert (await client.post("/api/tickets/999999/similar", headers=headers)).status_code == 404
