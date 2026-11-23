import json

import httpx2
import pytest

from app.integrations.embeddings import EmbeddingClient, EmbeddingError


def test_embedding_adapter_preserves_input_order_and_checks_dimensions():
    def reply(request):
        payload = json.loads(request.content)
        assert payload["input"] == ["登录失败", "账单异常"]
        assert payload["dimensions"] == 4
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "model": "test-model",
                "data": [
                    {"object": "embedding", "index": 1, "embedding": [0, 1, 0, 0]},
                    {"object": "embedding", "index": 0, "embedding": [1, 0, 0, 0]},
                ],
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            },
        )

    with EmbeddingClient(
        "https://model.example/v1",
        "synthetic-key",
        "test-model",
        4,
        http_client=httpx2.Client(transport=httpx2.MockTransport(reply)),
    ) as model:
        assert model.embed(["登录失败", "账单异常"]) == [[1, 0, 0, 0], [0, 1, 0, 0]]


def test_embedding_upstream_error_is_not_a_successful_empty_result():
    calls = []

    def reply(request):
        calls.append(request)
        return httpx2.Response(429, json={"error": {"message": "rate limit", "type": "limit"}})

    with EmbeddingClient(
        "https://model.example/v1",
        "synthetic-key",
        "test-model",
        4,
        http_client=httpx2.Client(transport=httpx2.MockTransport(reply)),
    ) as model:
        with pytest.raises(EmbeddingError, match="429"):
            model.embed(["登录失败"])
    assert len(calls) == 1


@pytest.mark.parametrize(
    "data",
    [
        [{"index": 0, "embedding": [1.0, 0.0]}],
        [{"index": 1, "embedding": [1.0, 0.0, 0.0, 0.0]}],
        [{"index": 0, "embedding": [0.0, 0.0, 0.0, 0.0]}],
        [{"index": 0, "embedding": None}],
        [],
    ],
)
def test_malformed_embedding_response_is_rejected(data):
    def reply(request):
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "model": "test-model",
                "data": data,
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )

    with EmbeddingClient(
        "https://model.example/v1",
        "synthetic-key",
        "test-model",
        4,
        http_client=httpx2.Client(transport=httpx2.MockTransport(reply)),
    ) as model:
        with pytest.raises(EmbeddingError):
            model.embed(["登录失败"])
