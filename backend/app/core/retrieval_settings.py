from pathlib import Path

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RetrievalSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env.retrieval",
        env_file_encoding="utf-8",
        hide_input_in_errors=True,
    )
    milvus_db_path: Path
    model_base_url: AnyHttpUrl
    model_api_key: SecretStr = Field(min_length=1)
    embedding_model: str = Field(min_length=1)
    embedding_dimensions: int = Field(ge=1, le=4096)

    @field_validator("milvus_db_path")
    @classmethod
    def absolute_database_path(cls, value: Path) -> Path:
        if not value.is_absolute() or value.suffix != ".db":
            raise ValueError("MILVUS_DB_PATH 必须是以 .db 结尾的 WSL 绝对路径")
        return value

    @field_validator("model_base_url")
    @classmethod
    def credentials_belong_in_key(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.username or value.password or value.query or value.fragment:
            raise ValueError("MODEL_BASE_URL 不得包含账号、密码、查询参数或片段")
        return value
