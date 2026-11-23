from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr, ValidationError
from pydantic_settings import SettingsConfigDict

from app import seed
from app.core.settings import Settings
from app.main import create_app


class IsolatedSettings(Settings):
    model_config = SettingsConfigDict(env_file=None)


def make_test_settings() -> Settings:
    return IsolatedSettings(
        database_url=SecretStr("postgresql+psycopg://unit:unit@127.0.0.1:1/unit_unused"),
        jwt_secret=SecretStr("unit-test-signing-key-not-used-outside-tests"),
        access_token_minutes=60,
    )


@asynccontextmanager
async def app_client() -> AsyncIterator[AsyncClient]:
    app = create_app(make_test_settings(), recover_jobs=False)
    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def test_health_without_database_connection() -> None:
    async with app_client() as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]


async def test_login_required_error_contract() -> None:
    async with app_client() as client:
        response = await client.get("/api/users")
    assert response.status_code == 401
    assert response.json()["message"] == "请登录或重新登录"
    assert response.json()["code"] == "HTTP_401"
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert response.headers["www-authenticate"] == "Bearer"


async def test_validation_does_not_echo_password() -> None:
    async with app_client() as client:
        response = await client.post("/api/auth/login", json={"username": "admin", "password": "x9Q!"})
    assert response.status_code == 422
    assert "x9Q!" not in response.text
    assert response.json()["detail"][0]["loc"] == ["body", "password"]
    assert response.json()["detail"][0]["msg"] == "长度不足"


@pytest.mark.parametrize(
    ("username", "password", "field"),
    [("admin", "x9Q!", "password"), ("invalid-name", "Only-for-unit-123", "username")],
)
def test_seed_invalid_input_is_private(
    monkeypatch: pytest.MonkeyPatch, username: str, password: str, field: str
) -> None:
    monkeypatch.setattr("sys.argv", ["seed", "--username", username, "--display-name", "测试管理员"])
    monkeypatch.setattr(seed, "getpass", lambda prompt: password)
    with pytest.raises(SystemExit) as error:
        seed.main()
    assert field in str(error.value)
    assert password not in str(error.value)


def test_settings_validate_limits_and_hide_secrets() -> None:
    with pytest.raises(ValidationError) as error:
        IsolatedSettings(
            database_url=SecretStr("sqlite:///invalid"),
            jwt_secret=SecretStr("private-key-too-short"), access_token_minutes=0,
        )
    assert "private-key-too-short" not in str(error.value)


def test_default_login_token_lasts_eight_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    import jwt

    from app.core.security import create_access_token

    monkeypatch.delenv("ACCESS_TOKEN_MINUTES", raising=False)
    config = IsolatedSettings(
        database_url=SecretStr("postgresql+psycopg://unit:unit@127.0.0.1:1/unit_unused"),
        jwt_secret=SecretStr("unit-test-signing-key-not-used-outside-tests"),
    )
    token = create_access_token(1, config)
    claims = jwt.decode(token, config.jwt_secret.get_secret_value(), algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == 8 * 60 * 60
