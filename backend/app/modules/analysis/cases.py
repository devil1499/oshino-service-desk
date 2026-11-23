import hashlib
import json

from app.models import Ticket


def case_text(ticket: Ticket) -> str:
    # 检索使用有限长度摘录；详情页仍展示 PostgreSQL 中的完整原文。
    return f"标题：{ticket.title}\n问题：{ticket.description[:3000]}\n解决方案：{ticket.solution[:3000]}"


def case_fingerprint(ticket: Ticket) -> str:
    content = [
        ticket.title,
        ticket.description,
        ticket.solution,
        ticket.product_id,
        ticket.module_id,
        ticket.category_id,
    ]
    return hashlib.sha256(json.dumps(content, ensure_ascii=False).encode()).hexdigest()


def case_row(ticket: Ticket, vector: list[float]) -> dict:
    return {
        "ticket_id": ticket.id,
        "content": case_text(ticket),
        "dense_vector": vector,
        "product_id": ticket.product_id,
        "module_id": ticket.module_id,
        "category_id": ticket.category_id,
        "fingerprint": case_fingerprint(ticket),
    }
