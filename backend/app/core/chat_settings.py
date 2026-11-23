from pathlib import Path

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChatSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env.chat",
        env_file_encoding="utf-8",
        hide_input_in_errors=True,
    )
    chat_base_url: AnyHttpUrl
    chat_api_key: SecretStr = Field(min_length=1)
    chat_model: str = Field(min_length=1)

    @field_validator("chat_base_url")
    @classmethod
    def validate_base_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.username or value.password or value.query or value.fragment:
            raise ValueError("CHAT_BASE_URL 不得包含账号、密码或查询参数")
        return value
