import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("evaluate", Path(__file__).resolve().parents[2] / "scripts/evaluate.py")
assert spec is not None and spec.loader is not None
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)


def test_recall_uses_all_relevant_cases_as_denominator():
    assert evaluate.recall_at_five([1, 2, 8, 9, 10, 3], [1, 2, 3, 4]) == 0.5


def test_macro_f1_includes_missed_class():
    assert evaluate.macro_f1([1, 1, 2, 2], [1, 1, 1, 1]) == 1 / 3
