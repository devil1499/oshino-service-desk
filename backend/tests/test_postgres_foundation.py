import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jwt
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from httpx import ASGITransport, AsyncClient
from psycopg import sql
from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict
from sqlalchemy import inspect
from sqlalchemy.engine import URL, make_url

from app.core.database import create_database_engine
from app.core.settings import Settings
from app.main import create_app
from app.modules.users.schemas import UserCreate
from app.seed import CATEGORIES, create_admin

pytestmark = pytest.mark.postgres
BACKEND = Path(__file__).resolve().parents[1]
TEST_PASSWORD = "Only-for-test-8392"


class IsolatedSettings(Settings):
    model_config = SettingsConfigDict(env_file=None)


def migrate(settings: Settings, revision: str = "head", downgrade: bool = False) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    config.attributes["database_url"] = settings.database_url.get_secret_value()
    if downgrade:
        command.downgrade(config, revision)
    else:
        command.upgrade(config, revision)


def create_test_database() -> tuple[URL, URL]:
    value = os.environ.get("TEST_DATABASE_URL") or dotenv_values(BACKEND / ".env.test").get("TEST_DATABASE_URL")
    if not value:
        pytest.skip("需要 backend/.env.test 或 TEST_DATABASE_URL 专用测试配置")
    base_url = make_url(value)
    if not base_url.database or not base_url.database.endswith("_test"):
        raise ValueError("测试地址必须指向以 _test 结尾的专用库，禁止连接业务库")
    url = base_url.set(database=f"after_sales_{uuid4().hex}_test")
    connection_url = base_url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(connection_url, autocommit=True) as db:
        db.execute(sql.SQL("CREATE DATABASE {} WITH TEMPLATE template0").format(sql.Identifier(url.database or "")))
    return base_url, url


def drop_test_database(base_url: URL, url: URL) -> None:
    name = url.database or ""
    if not name.startswith("after_sales_") or not name.endswith("_test") or name == base_url.database:
        raise ValueError("临时测试库名不符合约束，已拒绝清理")
    connection_url = base_url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(connection_url, autocommit=True) as db:
        db.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
async def database() -> AsyncIterator[Settings]:
    base_url, url = await asyncio.to_thread(create_test_database)
    settings = IsolatedSettings(
        database_url=SecretStr(url.render_as_string(hide_password=False)),
        jwt_secret=SecretStr("isolated-test-key-" + uuid4().hex), access_token_minutes=60,
    )
    try:
        await asyncio.to_thread(migrate, settings)
        yield settings
    finally:
        await asyncio.to_thread(drop_test_database, base_url, url)


@asynccontextmanager
async def app_client(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def admin_headers(client: AsyncClient, settings: Settings) -> dict[str, str]:
    await create_admin(settings, UserCreate(username="admin", display_name="测试管理员", password=TEST_PASSWORD))
    response = await client.post("/api/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    assert response.status_code == 200
    assert "password_hash" not in response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


async def test_staff_permissions_and_disable(database: Settings) -> None:
    async with app_client(database) as client:
        admin = await admin_headers(client, database)
        body = {"username": "staff", "display_name": "客服", "password": TEST_PASSWORD}
        created = await client.post("/api/users", headers=admin, json=body)
        assert created.status_code == 201
        assert "password_hash" not in created.json()
        assert (await client.post("/api/users", headers=admin, json=body)).status_code == 409
        forged = await client.post("/api/users", headers=admin, json={**body, "username": "forged", "role": "admin"})
        assert forged.status_code == 422
        login = await client.post("/api/auth/login", json={"username": "staff", "password": TEST_PASSWORD})
        assert login.status_code == 200
        staff = {"Authorization": "Bearer " + login.json()["access_token"]}
        assert (await client.get("/api/auth/me", headers=staff)).json()["role"] == "staff"
        assert (await client.get("/api/config/products", headers=staff)).status_code == 200
        assert (await client.post("/api/config/products", headers=staff, json={"name": "越权产品"})).status_code == 403
        assert (await client.post("/api/users", headers=staff, json={**body, "username": "denied"})).status_code == 403
        user_id = created.json()["id"]
        disabled = await client.patch(f"/api/users/{user_id}", headers=admin, json={"is_active": False})
        assert disabled.status_code == 200
        assert disabled.json()["is_active"] is False
        assert (await client.get("/api/auth/me", headers=staff)).status_code == 401
        assert (await client.post("/api/auth/login", json=body)).status_code == 422
        assert (await client.post(
            "/api/auth/login", json={"username": "staff", "password": TEST_PASSWORD}
        )).status_code == 403
        assert (await client.patch("/api/users/1", headers=admin, json={"is_active": False})).status_code == 409


async def test_wrong_expired_and_forged_credentials(database: Settings) -> None:
    async with app_client(database) as client:
        admin = await admin_headers(client, database)
        wrong = await client.post("/api/auth/login", json={"username": "admin", "password": "Wrong-password-123"})
        assert wrong.status_code == 401
        assert "Wrong-password-123" not in wrong.text
        assert (await client.get("/api/auth/me", headers={"Authorization": "Bearer invalid"})).status_code == 401
        now = datetime.now(UTC)
        expired = jwt.encode(
            {"sub": "1", "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1)},
            database.jwt_secret.get_secret_value(), algorithm="HS256",
        )
        assert (await client.get("/api/auth/me", headers={"Authorization": "Bearer " + expired})).status_code == 401
        assert (await client.get("/api/users?page_size=101", headers=admin)).status_code == 422
        first = await client.get("/api/users?page=1&page_size=1", headers=admin)
        assert len(first.json()) == 1
        assert (await client.get("/api/users?page=2&page_size=1", headers=admin)).json() == []


@pytest.mark.parametrize("kind", ["products", "categories"])
async def test_named_config_lifecycle_and_persistence(database: Settings, kind: str) -> None:
    async with app_client(database) as client:
        admin = await admin_headers(client, database)
        created = await client.post(f"/api/config/{kind}", headers=admin, json={"name": "  示例配置  "})
        assert created.status_code == 201
        assert created.json()["name"] == "示例配置"
        duplicate = await client.post(f"/api/config/{kind}", headers=admin, json={"name": "示例配置"})
        assert duplicate.status_code == 409
        item_id = created.json()["id"]
        renamed = await client.put(
            f"/api/config/{kind}/{item_id}", headers=admin, json={"name": "修改后的配置", "is_active": False}
        )
        assert renamed.status_code == 200
        assert renamed.json()["is_active"] is False
    async with app_client(database) as client:
        login = await client.post("/api/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        rows = (await client.get(f"/api/config/{kind}", headers=headers)).json()
        assert any(row["id"] == item_id and row["name"] == "修改后的配置" for row in rows)
        assert (await client.put(
            f"/api/config/{kind}/99999", headers=headers, json={"name": "不存在", "is_active": True}
        )).status_code == 404


async def test_module_foreign_key_and_name_scope(database: Settings) -> None:
    async with app_client(database) as client:
        admin = await admin_headers(client, database)
        first = (await client.post("/api/config/products", headers=admin, json={"name": "产品一"})).json()
        second = (await client.post("/api/config/products", headers=admin, json={"name": "产品二"})).json()
        body = {"name": "账号模块", "product_id": first["id"]}
        module = await client.post("/api/config/modules", headers=admin, json=body)
        assert module.status_code == 201
        assert module.json()["product_id"] == first["id"]
        assert (await client.post("/api/config/modules", headers=admin, json=body)).status_code == 409
        assert (await client.post(
            "/api/config/modules", headers=admin, json={**body, "product_id": second["id"]}
        )).status_code == 201
        assert (await client.post(
            "/api/config/modules", headers=admin, json={**body, "product_id": 99999}
        )).status_code == 422
        await client.put(
            f"/api/config/products/{first['id']}", headers=admin, json={"name": "产品一", "is_active": False}
        )
        assert (await client.post(
            "/api/config/modules", headers=admin, json={"name": "新模块", "product_id": first["id"]}
        )).status_code == 422
        renamed = await client.put(
            f"/api/config/modules/{module.json()['id']}", headers=admin,
            json={"name": "账号管理", "is_active": False},
        )
        assert renamed.status_code == 200
        assert renamed.json()["product_id"] == first["id"]
        assert renamed.json()["is_active"] is False


async def test_seed_does_not_overwrite_and_migration_round_trip(database: Settings) -> None:
    body = UserCreate(username="admin", display_name="管理员", password=TEST_PASSWORD)
    await create_admin(database, body)
    with pytest.raises(ValueError, match="用户名已存在"):
        await create_admin(database, body)
    async with app_client(database) as client:
        login = await client.post("/api/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        rows = (await client.get("/api/config/categories", headers=headers)).json()
        assert {row["name"] for row in rows} == set(CATEGORIES)
    await asyncio.to_thread(migrate, database, "base", True)
    engine = create_database_engine(database.database_url)
    try:
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
        assert tables == ["alembic_version"]
    finally:
        await engine.dispose()
    await asyncio.to_thread(migrate, database)
    config = Config(str(BACKEND / "alembic.ini"))
    config.attributes["database_url"] = database.database_url.get_secret_value()
    await asyncio.to_thread(command.check, config)
