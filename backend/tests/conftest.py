import pytest

from app.integrations.chat import ChatError


@pytest.fixture(autouse=True)
def isolate_saved_ai_settings(tmp_path, monkeypatch):
    # 网页保存的真实密钥不能进入测试模型调用；每项测试拥有独立配置路径。
    monkeypatch.setenv('AI_SETTINGS_PATH', str(tmp_path / 'ai/settings.json'))


@pytest.fixture(autouse=True)
def block_unexpected_model_calls(request, monkeypatch):
    if not request.node.get_closest_marker("postgres") or request.node.get_closest_marker("basic_analysis"):
        return

    class StubBasicChatClient:
        def __init__(self, base_url, api_key, model):
            self.model = model

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            pass

        def ask(self, instruction, data, result_type):
            raise ChatError("测试环境未调用真实聊天模型")

    monkeypatch.setattr("app.modules.analysis.basic.ChatClient", StubBasicChatClient)
