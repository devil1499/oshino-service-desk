import json

import httpx2 as httpx
import pytest
from pydantic import BaseModel

from app.integrations.chat import ChatClient, ChatError


class Answer(BaseModel):
    answer: str


@pytest.mark.parametrize("thinking", [None, False])
def test_chat_parses_json_and_disables_retries(thinking):
    def handler(request):
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        assert "只返回一个 JSON 对象" in body["messages"][0]["content"]
        assert "enable_thinking" not in body
        assert body.get("thinking") == (None if thinking is None else {"type": "disabled"})
        return httpx.Response(
            200,
            json={
                "id": "fixture",
                "object": "chat.completion",
                "created": 1,
                "model": "fixture",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": '{"answer":"检查角色"}'},
                    }
                ],
            },
        )

    with ChatClient(
        "https://model.example/v1", "fixture-key", "fixture", httpx.Client(transport=httpx.MockTransport(handler))
    ) as client:
        assert client.ask("返回JSON", {}, Answer, thinking=thinking).answer == "检查角色"


@pytest.mark.parametrize("content,finish", [("not json", "stop"), ("{}", "length")])
def test_chat_rejects_invalid_or_incomplete_response(content, finish):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "id": "fixture",
                "object": "chat.completion",
                "created": 1,
                "model": "fixture",
                "choices": [
                    {"index": 0, "finish_reason": finish, "message": {"role": "assistant", "content": content}}
                ],
            },
        )
    )
    with ChatClient("https://model.example/v1", "fixture-key", "fixture", httpx.Client(transport=transport)) as client:
        with pytest.raises(ChatError):
            client.ask("返回JSON", {}, Answer)


@pytest.mark.parametrize("status", [401, 429, 503])
def test_chat_preserves_http_failure_and_does_not_retry(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "upstream failure"}})

    with ChatClient(
        "https://model.example/v1", "fixture-key", "fixture", httpx.Client(transport=httpx.MockTransport(handler))
    ) as client:
        with pytest.raises(ChatError, match=f"HTTP {status}"):
            client.ask("返回JSON", {}, Answer)
    assert len(calls) == 1
