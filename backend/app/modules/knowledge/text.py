import hashlib
import json

from app.models import KnowledgeDocument


def split_text(content: str) -> list[str]:
    """按字符切分，块长500、重叠80；仅在确有余文时继续。"""
    chunks = []
    start = 0
    while start < len(content):
        chunks.append(content[start : start + 500])
        if start + 500 >= len(content):
            break
        start += 420
    return chunks


def document_fingerprint(document: KnowledgeDocument) -> str:
    values = [
        document.title,
        document.content,
        document.product_id,
        document.module_id,
        document.category_id,
        document.revision,
    ]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()
