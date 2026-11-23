import json

import pytest
from pydantic import ValidationError

from app.core.ai_settings import AiSettingsInput, AiSettingsStore
from app.core.chat_settings import ChatSettings


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    monkeypatch.setitem(ChatSettings.model_config, "env_file", None)
    for name in ("CHAT_BASE_URL", "CHAT_MODEL", "CHAT_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_settings_keep_keys_private_and_preserve_when_left_blank(tmp_path):
    store = AiSettingsStore(tmp_path / "private/settings.json")
    body = AiSettingsInput(
        chat_base_url="https://api.deepseek.com",
        chat_model="deepseek-chat",
        chat_api_key="private-test-key",
        search_enabled=True,
        search_reuse_chat_key=True,
    )
    view = store.save(body)
    assert view["chat_key_configured"] is True
    assert "private-test-key" not in json.dumps(view)
    assert store.chat().chat_api_key.get_secret_value() == "private-test-key"
    store.save(body.model_copy(update={"chat_api_key": ""}))
    assert store.search_key() == "private-test-key"
    assert json.loads(store.path.read_text())["chat_api_key"] == "private-test-key"


def test_incomplete_or_corrupt_settings_are_visible_errors(tmp_path):
    store = AiSettingsStore(tmp_path / "settings.json")
    with pytest.raises(ValueError, match="密钥"):
        store.save(AiSettingsInput(chat_base_url="https://api.deepseek.com", chat_model="deepseek-chat"))
    store.path.write_text("{broken")
    with pytest.raises(ValueError, match="配置文件"):
        store.view()
    with pytest.raises(ValidationError):
        AiSettingsInput(chat_base_url="https://user:pass@example.com", chat_model="model")
