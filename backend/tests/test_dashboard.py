from datetime import UTC, datetime, timedelta

import pytest
from test_import import csv_file, import_row
from test_knowledge_search import create_query
from test_postgres_foundation import database as database
from test_similar import retrieval as retrieval

from app.models import Ticket

pytestmark = pytest.mark.postgres


async def test_dashboard_counts_filters_and_real_resolution_time(retrieval):
    app, client, headers, catalog, _ = retrieval
    response = await client.get("/api/dashboard", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["average_resolution_hours"] is None
    ticket_id = await create_query(client, headers, catalog)
    path = f"/api/tickets/{ticket_id}"
    await client.post(path + "/start", headers=headers)
    await client.post(path + "/resolve", headers=headers, json={"solution": "重新绑定角色"})
    async with app.state.session_factory() as db:
        ticket = await db.get(Ticket, ticket_id)
        assert ticket.resolved_at is not None
        ticket.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        ticket.resolved_at = ticket.created_at + timedelta(hours=2)
        await db.commit()
    assert (
        await client.post(path + "/close", headers=headers, json={"customer_reply_confirmed": True})
    ).status_code == 200
    row = await import_row(client, headers, catalog)
    await client.post("/api/tickets/import", headers=headers, files=csv_file([row]))
    result = (await client.get("/api/dashboard", headers=headers)).json()
    assert result["total"] == 2
    assert result["by_status"]["closed"] >= 1
    assert sum(result["by_status"].values()) == sum(result["by_priority"].values()) == 2
    assert result["resolution_samples"] == 1
    assert result["average_resolution_hours"] == 2
    assert (await client.get("/api/dashboard?product_id=99999", headers=headers)).json()["total"] == 0
    assert (await client.get("/api/dashboard")).status_code == 401
    assert (await client.get("/api/dashboard?product_id=0", headers=headers)).status_code == 422
