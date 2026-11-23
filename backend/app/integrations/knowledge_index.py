from pathlib import Path

from app.integrations.hybrid_index import HybridIndex


class KnowledgeIndex(HybridIndex):
    def __init__(self, path: Path, model: str, base_url: str, dimensions: int):
        super().__init__(
            path, model, base_url, dimensions, "knowledge_chunks", "chunk_id", Path(str(path) + ".knowledge.index.json")
        )
