import asyncio
import json

import httpx2 as httpx
import pytest
from pydantic import BaseModel

from app.integrations.chat import ChatClient, ChatError
from app.modules.qa.adapters import model_adapter
from app.modules.qa.trace import RunTrace, redact


class Reply(BaseModel):
    answer: str


def response(usage=None, content='{"answer":"检查角色"}'):
    return {
        "id": "fixture",
        "object": "chat.completion",
        "created": 1,
        "model": "fixture",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
        "usage": usage,
    }


async def test_all_calls_count_actual_usage_even_when_json_validation_fails():
    replies = [
        response({"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}),
        response(None),
        response({"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11}, "bad json"),
    ]
    trace = RunTrace("fixture", "qa-v1", {"text": "登录失败", "history": []})
    with ChatClient(
        "https://fixture.example/v1",
        "never-store-key",
        "fixture",
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=replies.pop(0)))),
    ) as chat:
        call = model_adapter(chat, trace)
        await call("返回回答", {"question": "登录失败"}, Reply)
        await call("返回回答", {"question": "继续"}, Reply)
        with pytest.raises(ChatError):
            await call("返回回答", {"question": "再试"}, Reply)
    snapshot = trace.snapshot()
    assert snapshot["usage"]["chat"] == {
        "calls": 3,
        "known_calls": 2,
        "input_tokens": 18,
        "output_tokens": 7,
        "total_tokens": 25,
        "complete": False,
    }
    assert snapshot["calls"][2]["status"] == "failed"
    assert snapshot["calls"][0]["request"]["messages"][0]["role"] == "system"
    assert "never-store-key" not in json.dumps(snapshot)


async def test_failed_transport_has_unknown_usage_and_concurrent_traces_stay_separate():
    async def run(text):
        trace = RunTrace("fixture", "qa-v1", {"text": text, "history": []})
        with ChatClient(
            "https://fixture.example/v1",
            "key",
            "fixture",
            httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))),
        ) as chat:
            with pytest.raises(ChatError):
                await model_adapter(chat, trace)("回答", {"text": text}, Reply)
        return trace.snapshot()

    a, b = await asyncio.gather(run("问题甲"), run("问题乙"))
    assert a["usage"]["chat"]["total_tokens"] is None
    assert a["usage"]["chat"]["complete"] is False
    assert "问题乙" not in json.dumps(a, ensure_ascii=False)
    assert "问题甲" not in json.dumps(b, ensure_ascii=False)


def test_trace_redacts_contact_and_explicit_credentials_without_changing_source_ids():
    value = redact(
        {"api_key": "private", "text": "邮箱 test@example.com 手机13800138000 密码：abc123", "source_id": "K101"}
    )
    assert value["api_key"] == "[已脱敏]"
    assert "test@example.com" not in value["text"]
    assert "13800138000" not in value["text"]
    assert "abc123" not in value["text"]
    assert value["source_id"] == "K101"
    assert "private-secret" not in redact('{"password": "private-secret"}')


@pytest.mark.parametrize("fails", [False, True])
async def test_transaction_step_keeps_trace_without_borrowing_a_checkpoint_connection(fails):
    checkpoints = []

    async def checkpoint(snapshot):
        checkpoints.append(snapshot)

    async def verify(data):
        assert data == {"sources": ["K1"]}
        if fails:
            raise ValueError("source changed")
        return {"verified_sources": 1}

    trace = RunTrace("fixture", "qa-v1", {"text": "验证引用", "history": []}, checkpoint)
    if fails:
        with pytest.raises(ValueError, match="source changed"):
            await trace.run_step("verify_sources", verify, {"sources": ["K1"]}, checkpoint=False)
    else:
        result = await trace.run_step("verify_sources", verify, {"sources": ["K1"]}, checkpoint=False)
        assert result == {"verified_sources": 1}

    assert checkpoints == []
    step = trace.snapshot()["steps"][0]
    assert step["duration_ms"] >= 0
    assert step["input"] == {"sources": ["K1"]}
    assert step["status"] == ("failed" if fails else "succeeded")
    assert step["output"] == (None if fails else {"verified_sources": 1})
    assert step["error"] == ("ValueError" if fails else None)
