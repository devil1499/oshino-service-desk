import pytest
from test_postgres_foundation import database as database, app_client, admin_headers, TEST_PASSWORD

pytestmark = pytest.mark.postgres


async def test_ai_settings_are_admin_only_and_do_not_expose_credentials(database, tmp_path, monkeypatch):
    monkeypatch.setenv("AI_SETTINGS_PATH", str(tmp_path / "private/settings.json"))
    async with app_client(database) as client:
        admin = await admin_headers(client, database)
        body = {
            "chat_base_url": "https://api.deepseek.com",
            "chat_model": "deepseek-chat",
            "chat_api_key": "private-fixture-key",
            "search_enabled": True,
            "search_reuse_chat_key": True,
        }
        assert (await client.get("/api/ai-service/settings")).status_code == 401
        saved = await client.put("/api/ai-service/settings", headers=admin, json=body)
        assert saved.status_code == 200, saved.text
        assert saved.json()["search_key_configured"]
        assert "private-fixture-key" not in saved.text
        assert "private-fixture-key" not in (await client.get("/api/ai-service/settings", headers=admin)).text
        await client.post(
            "/api/users",
            headers=admin,
            json={"username": "ai_staff", "display_name": "客服", "password": TEST_PASSWORD},
        )
        login = await client.post("/api/auth/login", json={"username": "ai_staff", "password": TEST_PASSWORD})
        staff = {"Authorization": "Bearer " + login.json()["access_token"]}
        assert (await client.get("/api/ai-service/settings", headers=staff)).status_code == 403
        assert (await client.put("/api/ai-service/settings", headers=staff, json=body)).status_code == 403
        assert (await client.get("/api/ai-service/capabilities", headers=staff)).json() == {
            "web_search_available": True
        }
