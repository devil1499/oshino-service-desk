"""网页配置的私有文件；只有未保存过时沿用原 .env.chat。"""

import os
import tempfile
import threading
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from app.core.chat_settings import ChatSettings

_save_lock = threading.Lock()


class AiConfigurationError(ValueError):
    pass


class AiSettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    chat_base_url: str
    chat_model: str = Field(min_length=1, max_length=200)
    chat_api_key: str = Field(default="", max_length=1000)
    search_enabled: bool = False
    search_reuse_chat_key: bool = True
    search_api_key: str = Field(default="", max_length=1000)

    def model_post_init(self, context):
        # 共用现有 URL 约束，禁止地址中夹带凭据与查询参数。
        ChatSettings(
            chat_base_url=self.chat_base_url,
            chat_model=self.chat_model,
            chat_api_key=SecretStr("validation-only"),
            _env_file=None,
        )


class AiSettingsStore:
    def __init__(self, path: Path):
        self.path = path

    def read(self) -> dict | None:
        if not self.path.exists():
            return None
        try:
            data = AiSettingsInput.model_validate_json(self.path.read_text(encoding="utf-8"))
            self.validate_keys(data)
        except (ValidationError, ValueError) as error:
            raise AiConfigurationError("AI 服务配置文件格式错误，请由管理员重新配置") from error
        return data.model_dump()

    def effective(self) -> dict:
        saved = self.read()
        if saved is not None:
            return saved
        try:
            legacy = ChatSettings.model_validate({})
        except ValidationError:
            return dict(
                chat_base_url="",
                chat_model="",
                chat_api_key="",
                search_enabled=False,
                search_reuse_chat_key=True,
                search_api_key="",
            )
        return dict(
            chat_base_url=str(legacy.chat_base_url),
            chat_model=legacy.chat_model,
            chat_api_key=legacy.chat_api_key.get_secret_value(),
            search_enabled=False,
            search_reuse_chat_key=True,
            search_api_key="",
        )

    def view(self) -> dict:
        data = self.effective()
        return {
            key: data[key] for key in ("chat_base_url", "chat_model", "search_enabled", "search_reuse_chat_key")
        } | {
            "chat_key_configured": bool(data["chat_api_key"]),
            "search_key_configured": bool(
                data["chat_api_key"] if data["search_reuse_chat_key"] else data["search_api_key"]
            ),
        }

    @staticmethod
    def validate_keys(data: AiSettingsInput):
        if not data.chat_api_key.strip():
            raise AiConfigurationError("请填写聊天 API 密钥")
        if (
            data.search_enabled
            and not (data.chat_api_key if data.search_reuse_chat_key else data.search_api_key).strip()
        ):
            raise AiConfigurationError("启用搜索需要填写 DeepSeek 搜索密钥")

    def save(self, body: AiSettingsInput) -> dict:
        with _save_lock:
            # 配置损坏时允许管理员用完整新配置修复，不用空配置掩盖错误。
            try:
                previous = self.effective()
            except AiConfigurationError:
                if not body.chat_api_key or (
                    body.search_enabled and not body.search_reuse_chat_key and not body.search_api_key
                ):
                    raise
                previous = {}
            data = body.model_copy(
                update={
                    key: getattr(body, key).strip() or previous.get(key, "")
                    for key in ("chat_api_key", "search_api_key")
                }
            )
            self.validate_keys(data)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=self.path.parent, delete=False
                ) as file:
                    temporary = Path(file.name)
                    file.write(data.model_dump_json())
                    file.flush()
                    os.fsync(file.fileno())
                temporary.chmod(0o600)
                temporary.replace(self.path)
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()
        return self.view()

    def chat(self) -> ChatSettings:
        data = self.effective()
        if not data["chat_api_key"]:
            raise AiConfigurationError("请在管理中心 → AI 服务配置聊天模型，或填写 backend/.env.chat")
        return ChatSettings(
            chat_base_url=data["chat_base_url"],
            chat_model=data["chat_model"],
            chat_api_key=SecretStr(data["chat_api_key"]),
            _env_file=None,
        )

    def search_key(self) -> str:
        data = self.effective()
        if not data["search_enabled"]:
            raise AiConfigurationError("管理员尚未启用 DeepSeek 联网搜索")
        return data["chat_api_key"] if data["search_reuse_chat_key"] else data["search_api_key"]


def get_ai_store() -> AiSettingsStore:
    default = Path(__file__).resolve().parents[3] / ".local/ai-service/settings.json"
    return AiSettingsStore(Path(os.environ.get("AI_SETTINGS_PATH", str(default))))


def load_chat_settings() -> ChatSettings:
    return get_ai_store().chat()
