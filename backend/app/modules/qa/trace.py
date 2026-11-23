"""问答运行过程单：记录实际执行和快照，不推测缺失的模型用量。"""

import asyncio
import json
import re
import time
from datetime import UTC, datetime

from pydantic import BaseModel

from app.integrations.observation import current_call

PRIVATE_KEYS = {"password", "password_hash", "api_key", "authorization", "access_token", "jwt_secret", "secret"}


def redact(value):
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {
            str(key): "[已脱敏]" if str(key).lower() in PRIVATE_KEYS else redact(item) for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        # Chat 请求中的 user.content 是 JSON 字符串；按结构脱敏其凭据字段。
        if value.lstrip().startswith(("{", "[")):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                pass
            else:
                return json.dumps(redact(parsed), ensure_ascii=False)
        value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[邮箱已脱敏]", value)
        value = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[手机号已脱敏]", value)
        value = re.sub(r"(?i)\b(?:sk-[\w-]{8,}|Bearer\s+[\w.~-]+)", "[凭据已脱敏]", value)
        value = re.sub(
            r'(?i)((?:密码|验证码|授权码|api[_ -]?key|password|token)\s*(?:[:：=]|是|为)\s*)[^\s,，。;；"\'}]+',
            r"\1[已脱敏]",
            value,
        )
    return value


def usage_summary(calls: list[dict], kind: str) -> dict:
    selected = [call for call in calls if call["kind"] == kind]
    fields = (
        ["input_tokens", "total_tokens"] if kind == "embedding" else ["input_tokens", "output_tokens", "total_tokens"]
    )
    known = sum(
        all(call["usage"] is not None and call["usage"].get(field) is not None for field in fields) for call in selected
    )
    result = {"calls": len(selected), "known_calls": known, "complete": known == len(selected)}
    for field in ["input_tokens", "output_tokens", "total_tokens"]:
        counts = [
            call["usage"][field]
            for call in selected
            if call["usage"] is not None and call["usage"].get(field) is not None
        ]
        result[field] = sum(counts) if counts else (0 if not selected and field in fields else None)
    return result


class RunTrace:
    def __init__(self, model: str, prompt_version: str, question: dict, checkpoint=None):
        self.started = time.monotonic()
        self.checkpoint = checkpoint
        self.data = {
            "schema_version": 1,
            "started_at": datetime.now(UTC).isoformat(),
            "status": "running",
            "duration_ms": 0,
            "model": model,
            "prompt_version": prompt_version,
            "question": question,
            "steps": [],
            "calls": [],
            "sources": [],
            "error": None,
        }

    def snapshot(self) -> dict:
        self.data["duration_ms"] = round((time.monotonic() - self.started) * 1000)
        self.data["usage"] = {kind: usage_summary(self.data["calls"], kind) for kind in ("chat", "embedding")}
        return redact(self.data)

    async def persist(self):
        if self.checkpoint is not None:
            await self.checkpoint(self.snapshot())

    async def run_step(self, name, operation, data, *, checkpoint=True):
        started = time.monotonic()
        step = {"name": name, "status": "running", "duration_ms": 0, "input": data, "output": None, "error": None}
        self.data["steps"].append(step)
        if checkpoint:
            await self.persist()
        try:
            result = await operation(data)
            step.update(status="succeeded", output=result)
            return result
        except (Exception, asyncio.CancelledError) as error:
            # 只记录类型，未知异常正文可能含配置值；对用户的准确错误由 service 映射。
            step.update(status="failed", error=type(error).__name__)
            raise
        finally:
            step["duration_ms"] = round((time.monotonic() - started) * 1000)
            if checkpoint:
                await self.persist()

    async def call(self, kind, model, operation, *args):
        call = {
            "kind": kind,
            "model": model,
            "status": "running",
            "duration_ms": 0,
            "request": None,
            "response": None,
            "usage": None,
            "error": None,
        }
        self.data["calls"].append(call)
        await self.persist()
        started = time.monotonic()
        token = current_call.set(call)
        try:
            result = await asyncio.to_thread(operation, *args)
            call["response"] = result.model_dump(mode="json") if isinstance(result, BaseModel) else None
            call["status"] = "succeeded"
            return result
        except (Exception, asyncio.CancelledError) as error:
            call.update(status="failed", error=type(error).__name__)
            raise
        finally:
            current_call.reset(token)
            call["duration_ms"] = round((time.monotonic() - started) * 1000)

    def finish(self, status: str, *, sources=None, error=None):
        self.data["status"] = status
        self.data["sources"] = sources or []
        self.data["error"] = error
