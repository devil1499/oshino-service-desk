from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        hide_input_in_errors=True,
    )

    database_url: SecretStr
    jwt_secret: SecretStr = Field(min_length=32)
    access_token_minutes: int = Field(default=480, ge=1, le=1440)

    @classmethod
    def load(cls) -> "Settings":
        return cls.model_validate({})

    @model_validator(mode="after")
    def validate_database_url(self) -> "Settings":
        try:
            url = make_url(self.database_url.get_secret_value())
        except ArgumentError:
            raise ValueError("数据库连接地址格式不正确") from None
        if url.drivername != "postgresql+psycopg" or not url.database or not url.username:
            raise ValueError("请配置包含用户名和库名的 postgresql+psycopg 连接地址")
        return self
