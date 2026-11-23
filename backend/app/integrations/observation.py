"""按当前调用采集请求与用量；ContextVar 隔离并发问答及工作线程。"""

from contextvars import ContextVar

current_call: ContextVar[dict | None] = ContextVar("model_call", default=None)


def record_request(request: dict) -> None:
    call = current_call.get()
    if call is not None:
        call["request"] = request


def record_usage(response: dict, *, embedding: bool = False) -> None:
    call = current_call.get()
    if call is None:
        return
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return

    def count(name):
        value = usage.get(name)
        return value if type(value) is int and value >= 0 else None

    call["usage"] = {
        "input_tokens": count("prompt_tokens"),
        # Embedding 不生成文本，输出 Token 在这个接口中不适用。
        "output_tokens": None if embedding else count("completion_tokens"),
        "total_tokens": count("total_tokens"),
    }
    if isinstance(response.get("model"), str):
        call["model"] = response["model"]
