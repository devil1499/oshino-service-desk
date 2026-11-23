from pathlib import Path

from app.integrations.hybrid_index import HybridIndex, IndexNotReady  # noqa: F401

COLLECTION = "ticket_cases"


class CaseIndex(HybridIndex):
    def __init__(self, path: Path, model: str, base_url: str, dimensions: int):
        super().__init__(path, model, base_url, dimensions, COLLECTION, "ticket_id", Path(str(path) + ".index.json"))
