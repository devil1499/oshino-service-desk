"""报告切分对标注证据的完整覆盖情况；这不是检索召回率。"""

import argparse
import json
from collections import defaultdict
from pathlib import Path


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                yield json.loads(line)


def evaluate(dataset: Path) -> dict:
    answers = list(read_jsonl(dataset / "answers.jsonl"))
    if not answers:
        raise ValueError("没有带证据标注的检索问题")
    report = {}
    for strategy in ("fixed-500-80", "dialogue-turns"):
        chunks = list(read_jsonl(dataset / f"chunks-{strategy}.jsonl"))
        by_document = defaultdict(list)
        for chunk in chunks:
            by_document[chunk["document_id"]].append(set(chunk["complete_utterance_ids"]))
        full_coverage = 0
        single_chunk = 0
        for answer in answers:
            gold = set(answer["relevant_utterance_ids"])
            candidates = by_document[answer["document_id"]]
            if gold <= set().union(*candidates):
                full_coverage += 1
            if any(gold <= candidate for candidate in candidates):
                single_chunk += 1
        report[strategy] = {
            "questions": len(answers), "chunks": len(chunks),
            "average_chunk_length": round(sum(len(item["text"]) for item in chunks) / len(chunks), 1),
            "evidence_available_rate": round(full_coverage / len(answers), 4),
            "single_chunk_evidence_rate": round(single_chunk / len(answers), 4),
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="转换后的 val 或 test 目录")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.dataset), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
