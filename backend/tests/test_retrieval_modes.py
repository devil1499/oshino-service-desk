import pytest
from test_import import csv_file, import_row
from test_knowledge_search import create_query
from test_postgres_foundation import database as database
from test_similar import build_index
from test_similar import retrieval as retrieval

from app.modules.analysis.router import get_embedding_client

pytestmark = pytest.mark.postgres


async def test_each_mode_and_bm25_without_embedding(retrieval):
    app, client, headers, catalog, config = retrieval
    row = await import_row(client, headers, catalog)
    ids = (await client.post("/api/tickets/import", headers=headers, files=csv_file([row]))).json()["ticket_ids"]
    await build_index(app, config, ids)
    ticket_id = await create_query(client, headers, catalog)
    for mode in ["dense", "hybrid"]:
        response = await client.post(f"/api/tickets/{ticket_id}/similar?mode={mode}", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["items"][0]["id"] == ids[0]

    class NoEmbedding:
        def embed(self, texts):
            raise AssertionError("BM25 must not call embedding")

    app.dependency_overrides[get_embedding_client] = lambda: NoEmbedding()
    response = await client.post(f"/api/tickets/{ticket_id}/similar?mode=bm25", headers=headers)
    assert response.status_code == 200, response.text
    assert (await client.post(f"/api/tickets/{ticket_id}/similar?mode=unknown", headers=headers)).status_code == 422
