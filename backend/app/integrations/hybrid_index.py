import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pymilvus import AnnSearchRequest, DataType, Function, FunctionType, MilvusClient, RRFRanker


class IndexNotReady(RuntimeError):
    """缺少完整索引，或当前配置与构建时不一致。"""


class HybridIndex:
    def __init__(
        self,
        path: Path,
        model: str,
        base_url: str,
        dimensions: int,
        collection: str,
        primary_key: str,
        metadata_path: Path,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.collection = collection
        self.primary_key = primary_key
        self.metadata_path = metadata_path
        self.signature = {"model": model, "base_url": base_url.rstrip("/"), "dimensions": dimensions}
        self.dimensions = dimensions
        self.client = MilvusClient(str(path), timeout=10.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await asyncio.to_thread(self.client.close)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.client.close()

    def ready(self) -> dict:
        if not self.metadata_path.is_file():
            raise IndexNotReady("检索索引尚未完整建立，请运行重建命令")
        metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        if any(metadata[key] != value for key, value in self.signature.items()):
            raise IndexNotReady("Embedding 模型、地址或维度已变更，请重建索引")
        if not self.client.has_collection(self.collection):
            raise IndexNotReady("索引元数据存在，但检索集合缺失，请重建索引")
        return metadata

    def reset(self) -> None:
        # 仅在后端停止后重建派生索引。先撤销就绪标记，失败时不能查询半套数据。
        self.metadata_path.unlink(missing_ok=True)
        if self.client.has_collection(self.collection):
            self.client.drop_collection(self.collection)
        schema = self.client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(self.primary_key, DataType.INT64, is_primary=True)
        schema.add_field(
            "content", DataType.VARCHAR, max_length=65535, enable_analyzer=True, analyzer_params={"tokenizer": "jieba"}
        )
        schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=self.dimensions)
        schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)
        for field in ["product_id", "module_id", "category_id"]:
            schema.add_field(field, DataType.INT64)
        schema.add_field("fingerprint", DataType.VARCHAR, max_length=64)
        schema.add_function(
            Function(
                name="content_bm25",
                function_type=FunctionType.BM25,
                input_field_names=["content"],
                output_field_names=["sparse_vector"],
            )
        )
        indexes = self.client.prepare_index_params()
        indexes.add_index("dense_vector", index_type="FLAT", metric_type="COSINE")
        indexes.add_index("sparse_vector", index_type="SPARSE_INVERTED_INDEX", metric_type="BM25")
        self.client.create_collection(self.collection, schema=schema, index_params=indexes)

    def add(self, rows: list[dict]) -> None:
        self.client.insert(self.collection, rows)

    def finish(self, count: int) -> None:
        self.client.flush(self.collection)
        metadata = {**self.signature, "count": count, "built_at": datetime.now(UTC).isoformat()}
        temporary = self.metadata_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.metadata_path)

    def search(
        self, text: str, vector: list[float], expression: str,
        mode: Literal["bm25", "dense", "hybrid"] = "hybrid",
    ) -> list[dict]:
        self.ready()
        # 索引由独立命令构建；新进程打开已有集合后，需要加载才能检索。
        self.client.load_collection(self.collection)
        if mode != "hybrid":
            field = "sparse_vector" if mode == "bm25" else "dense_vector"
            query = text if mode == "bm25" else vector
            metric = "BM25" if mode == "bm25" else "COSINE"
            return self.client.search(
                self.collection, data=[query], anns_field=field,
                search_params={"metric_type": metric}, filter=expression,
                limit=20, output_fields=["fingerprint"],
            )[0]
        requests = [
            AnnSearchRequest([vector], "dense_vector", {"metric_type": "COSINE"}, limit=20, expr=expression),
            AnnSearchRequest([text], "sparse_vector", {"metric_type": "BM25"}, limit=20, expr=expression),
        ]
        return self.client.hybrid_search(
            self.collection,
            reqs=requests,
            ranker=RRFRanker(60),
            limit=20,
            output_fields=["fingerprint"],
        )[0]
