import asyncio

import httpx2
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from pydantic import BaseModel, ConfigDict, FiniteFloat, StrictInt, ValidationError

from app.integrations.observation import record_request, record_usage


class EmbeddingItem(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    index: StrictInt
    embedding: list[FiniteFloat]


class EmbeddingResponse(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    data: list[EmbeddingItem]


class EmbeddingError(RuntimeError):
    """模型调用失败，或返回结果不符合向量接口契约。"""


class EmbeddingClient:
    def __init__(
        self, base_url: str, api_key: str, model: str, dimensions: int, http_client: httpx2.Client | None = None
    ):
        self.model = model
        self.dimensions = dimensions
        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=30.0, max_retries=0, http_client=http_client)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await asyncio.to_thread(self.client.close)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.client.close()

    def embed(self, texts: list[str]) -> list[list[float]]:
        record_request({'input': texts, 'dimensions': self.dimensions})
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=texts,
                dimensions=self.dimensions,
                encoding_format="float",
            )
        except APITimeoutError as error:
            raise EmbeddingError("Embedding 请求超过 30 秒，请检查模型服务") from error
        except APIConnectionError as error:
            raise EmbeddingError("无法连接 Embedding 服务，请检查地址与网络") from error
        except APIStatusError as error:
            # 上游响应正文可能包含请求内容或凭据，不透传；保留准确的 HTTP 状态。
            raise EmbeddingError(f"Embedding 服务返回 HTTP {error.status_code}") from error
        record_usage(response.model_dump(), embedding=True)
        try:
            data = EmbeddingResponse.model_validate(response.model_dump()).data
        except ValidationError as error:
            raise EmbeddingError("Embedding 返回的数据结构或数值不合法") from error
        if len(data) != len(texts):
            raise EmbeddingError("Embedding 返回条数与输入不一致")
        items = sorted(data, key=lambda item: item.index)
        if [item.index for item in items] != list(range(len(texts))):
            raise EmbeddingError("Embedding 返回的 index 缺失或重复")
        vectors = [item.embedding for item in items]
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise EmbeddingError("Embedding 返回的维度与配置不一致")
            if not any(vector):
                raise EmbeddingError("Embedding 返回全零向量，无法计算余弦相似度")
        return vectors
