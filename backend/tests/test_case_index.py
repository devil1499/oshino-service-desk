import subprocess
import sys

import pytest

from app.integrations.case_index import CaseIndex, IndexNotReady


def case(case_id, text, vector, product=1, module=1, category=1):
    return {
        "ticket_id": case_id,
        "content": text,
        "dense_vector": vector,
        "product_id": product,
        "module_id": module,
        "category_id": category,
        "fingerprint": str(case_id),
    }


def test_real_milvus_dense_bm25_rrf_filter_and_persistence(tmp_path):
    path = tmp_path / "cases.db"
    with CaseIndex(path, "test-model", "https://model.example/v1", 4) as index:
        index.reset()
        index.add(
            [
                case(1, "账号登录错误 E401 密码重置", [1.0, 0.0, 0.0, 0.0]),
                case(2, "账单扣费重复退款", [0.0, 1.0, 0.0, 0.0]),
                case(3, "账号登录错误 E401", [1.0, 0.0, 0.0, 0.0], product=2),
            ]
        )
        index.finish(3)
        hits = index.search("登录 E401", [1.0, 0.0, 0.0, 0.0], "product_id == 1")
        assert hits[0]["ticket_id"] == 1
        assert {hit["ticket_id"] for hit in hits} == {1, 2}
        # 两路分别真实执行，确保混合查询中的关键词通道不是占位实现。
        keyword = index.client.search(
            "ticket_cases", data=["E401"], anns_field="sparse_vector", filter="product_id == 1", limit=5
        )
        assert keyword[0][0]["ticket_id"] == 1
    with CaseIndex(path, "test-model", "https://model.example/v1", 4) as index:
        assert index.ready()["count"] == 3
        assert index.search("账单退款", [0.0, 1.0, 0.0, 0.0], "product_id == 1")[0]["ticket_id"] == 2


def test_incomplete_index_and_changed_model_are_not_ready(tmp_path):
    path = tmp_path / "cases.db"
    with CaseIndex(path, "model-a", "https://model.example/v1", 4) as index:
        with pytest.raises(IndexNotReady):
            index.ready()
        index.reset()
        index.finish(0)
    with CaseIndex(path, "model-b", "https://model.example/v1", 4) as index:
        with pytest.raises(IndexNotReady, match="模型"):
            index.ready()
        index.reset()
        with pytest.raises(IndexNotReady):
            index.ready()


def test_index_built_in_another_process_can_be_searched(tmp_path):
    path = tmp_path / "separate.db"
    script = """
from pathlib import Path
import sys
from app.integrations.case_index import CaseIndex
with CaseIndex(Path(sys.argv[1]), 'test-model', 'https://model.example/v1', 4) as index:
    index.reset()
    index.add([{'ticket_id':1,'content':'登录错误 E401','dense_vector':[1.,0.,0.,0.],
                'product_id':1,'module_id':1,'category_id':1,'fingerprint':'test'}])
    index.finish(1)
"""
    subprocess.run([sys.executable, "-c", script, str(path)], check=True)
    with CaseIndex(path, "test-model", "https://model.example/v1", 4) as index:
        assert index.search("登录 E401", [1.0, 0.0, 0.0, 0.0], "product_id == 1")[0]["ticket_id"] == 1
