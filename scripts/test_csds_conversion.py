import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class CsdsConversionTests(unittest.TestCase):
    def test_retrieval_evaluation_ranks_the_labelled_answer_from_the_correct_dialogue(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / "source"
            output = base / "converted"
            source.mkdir()
            samples = [
                {
                    "DialogueID": 1,
                    "QA": [{"QueSumm": "用户询问退款办理办法。", "QueSummUttIDs": [0],
                            "AnsSummLong": "客服告知提交退款申请。", "AnsSummLongUttIDs": [1],
                            "intent": "退款"}],
                    "Dialogue": [
                        {"turn": 0, "speaker": "Q", "utterance": "退款 怎么 办理 ？"},
                        {"turn": 1, "speaker": "A", "utterance": "请 提交 退款 申请 。"},
                    ],
                },
                {
                    "DialogueID": 2,
                    "QA": [{"QueSumm": "用户询问登录办法。", "QueSummUttIDs": [0],
                            "AnsSummLong": "客服告知输入密码。", "AnsSummLongUttIDs": [1],
                            "intent": "登录"}],
                    "Dialogue": [
                        {"turn": 0, "speaker": "Q", "utterance": "登录 怎么 操作 ？"},
                        {"turn": 1, "speaker": "A", "utterance": "请 输入 密码 。"},
                    ],
                },
            ]
            for split in ("train", "val", "test"):
                (source / f"{split}.json").write_text(
                    json.dumps(samples, ensure_ascii=False), encoding="utf-8"
                )
            subprocess.run([sys.executable, str(ROOT / "convert_csds.py"), "--source", str(source),
                            "--output", str(output)], check=True, capture_output=True, text=True)
            result = subprocess.run([sys.executable, str(ROOT / "evaluate_csds_retrieval.py"),
                                     "--dataset", str(output / "val"), "--top-k", "1"],
                                    check=True, capture_output=True, text=True)
            report = json.loads(result.stdout)
            self.assertEqual(report["fixed-500-80"]["hit_at_1"], 1.0)
            self.assertEqual(report["dialogue-turns"]["evidence_recall_at_1"], 1.0)

    def test_converter_keeps_reference_answers_out_of_model_inputs_and_preserves_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / "source"
            output = base / "converted"
            source.mkdir()
            sample = {
                "DialogueID": 7,
                "QA": [
                    {"QueSumm": "用户询问能否退款。", "QueSummUttIDs": [0],
                     "AnsSummLong": "客服说明可以申请退款。", "AnsSummLongUttIDs": [1],
                     "intent": "退款"},
                    {"QueSumm": "用户询问预计到账时间。", "QueSummUttIDs": [2],
                     "AnsSummLong": "客服尚未回复。", "AnsSummLongUttIDs": [],
                     "intent": "退款"},
                ],
                "Dialogue": [
                    {"turn": 0, "speaker": "Q", "utterance": "我 想 退款 ， 可以 吗 ？"},
                    {"turn": 1, "speaker": "A", "utterance": "可以 申请 退款 。"},
                    {"turn": 2, "speaker": "Q", "utterance": "多久 到账 ？"},
                ],
            }
            for split in ("train", "val", "test"):
                (source / f"{split}.json").write_text(json.dumps([sample], ensure_ascii=False), encoding="utf-8")
            subprocess.run([sys.executable, str(ROOT / "convert_csds.py"), "--source", str(source),
                            "--output", str(output)], check=True, capture_output=True, text=True)

            document = read_jsonl(output / "val" / "documents.jsonl")[0]
            analysis = read_jsonl(output / "val" / "analysis.jsonl")
            queries = read_jsonl(output / "val" / "queries.jsonl")
            answers = read_jsonl(output / "val" / "answers.jsonl")
            self.assertEqual(len(analysis), 2)
            self.assertEqual(len(queries), 1)
            self.assertEqual(queries[0]["query_id"], answers[0]["query_id"])
            self.assertEqual(answers[0]["relevant_utterance_ids"], [1])
            self.assertNotIn("客服说明可以申请退款", json.dumps(queries, ensure_ascii=False))
            self.assertNotIn("客服说明可以申请退款", json.dumps(analysis[0]["input"], ensure_ascii=False))
            self.assertEqual(analysis[0]["reference"]["summary"], "用户询问能否退款。")
            self.assertIsNone(analysis[0]["reference"]["priority"])
            self.assertEqual(document["utterances"][1]["role"], "客服")
            self.assertEqual(document["text"][document["utterances"][1]["start"]:
                                               document["utterances"][1]["end"]], "可以申请退款。")
            self.assertEqual(len(read_jsonl(output / "test" / "queries.jsonl")), 1)

    def test_turn_chunks_keep_evidence_whole_when_fixed_length_splits_it(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / "source"
            output = base / "converted"
            source.mkdir()
            sample = {
                "DialogueID": 8,
                "QA": [{"QueSumm": "用户询问如何处理故障。", "QueSummUttIDs": [0],
                        "AnsSummLong": "客服给出处理办法。", "AnsSummLongUttIDs": [1], "intent": "故障"}],
                "Dialogue": [
                    {"turn": 0, "speaker": "Q", "utterance": "用" * 350},
                    {"turn": 1, "speaker": "A", "utterance": "答" * 350},
                ],
            }
            for split in ("train", "val", "test"):
                (source / f"{split}.json").write_text(json.dumps([sample], ensure_ascii=False), encoding="utf-8")
            subprocess.run([sys.executable, str(ROOT / "convert_csds.py"), "--source", str(source),
                            "--output", str(output)], check=True, capture_output=True, text=True)
            fixed = read_jsonl(output / "val" / "chunks-fixed-500-80.jsonl")
            turns = read_jsonl(output / "val" / "chunks-dialogue-turns.jsonl")
            self.assertFalse(any(1 in item["complete_utterance_ids"] for item in fixed))
            self.assertTrue(any(1 in item["complete_utterance_ids"] for item in turns))
            self.assertTrue(any(item["text"].startswith("[1] 客服：") for item in turns))
            self.assertEqual(fixed[0]["text"][-80:], fixed[1]["text"][:80])
            result = subprocess.run([sys.executable, str(ROOT / "evaluate_csds_chunks.py"),
                                     "--dataset", str(output / "val")],
                                    check=True, capture_output=True, text=True)
            report = json.loads(result.stdout)
            self.assertEqual(report["fixed-500-80"]["single_chunk_evidence_rate"], 0.0)
            self.assertEqual(report["dialogue-turns"]["single_chunk_evidence_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
