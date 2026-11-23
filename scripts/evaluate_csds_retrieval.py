"""用词面 BM25 对 CSDS 切分结果做离线检索评测，不调用正式知识库或向量模型。"""

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                yield json.loads(line)


def terms(text: str) -> Counter:
    tokens = []
    for part in re.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+", text.lower()):
        if "\u4e00" <= part[0] <= "\u9fff" and len(part) > 1:
            tokens.extend(part[index:index + 2] for index in range(len(part) - 1))
        else:
            tokens.append(part)
    return Counter(tokens)


def build_index(chunks: list[dict]):
    postings = defaultdict(list)
    lengths = []
    for index, chunk in enumerate(chunks):
        counts = terms(chunk["text"])
        lengths.append(sum(counts.values()))
        for term, count in counts.items():
            postings[term].append((index, count))
    return postings, lengths


def rank(query: str, chunks: list[dict], postings: dict, lengths: list[int], top_k: int) -> list[dict]:
    scores = defaultdict(float)
    average_length = sum(lengths) / len(lengths)
    for term in terms(query):
        matches = postings.get(term, ())
        inverse_frequency = math.log(1 + (len(chunks) - len(matches) + 0.5) / (len(matches) + 0.5))
        for index, frequency in matches:
            normalizer = frequency + 1.2 * (0.25 + 0.75 * lengths[index] / average_length)
            scores[index] += inverse_frequency * frequency * 2.2 / normalizer
    ranked = sorted(scores, key=lambda index: (-scores[index], chunks[index]["chunk_id"]))
    return [chunks[index] for index in ranked[:top_k]]


def evaluate(dataset: Path, top_k: int) -> dict:
    queries = list(read_jsonl(dataset / "queries.jsonl"))
    answers = {item["query_id"]: item for item in read_jsonl(dataset / "answers.jsonl")}
    if not queries or len(queries) != len(answers) or {item["query_id"] for item in queries} != set(answers):
        raise ValueError("检索问题与参考答案不匹配或为空")
    report = {}
    for strategy in ("fixed-500-80", "dialogue-turns"):
        chunks = list(read_jsonl(dataset / f"chunks-{strategy}.jsonl"))
        if not chunks:
            raise ValueError(f"{strategy} 没有切分结果")
        postings, lengths = build_index(chunks)
        hits = 0
        full_answers = 0
        total_recall = 0.0
        reciprocal_rank = 0.0
        for question in queries:
            answer = answers[question["query_id"]]
            gold = set(answer["relevant_utterance_ids"])
            if not gold:
                raise ValueError(f"{question['query_id']} 没有参考证据")
            retrieved = rank(question["query"], chunks, postings, lengths, top_k)
            found = set()
            for position, chunk in enumerate(retrieved, 1):
                if chunk["document_id"] != answer["document_id"]:
                    continue
                matched = gold & set(chunk["complete_utterance_ids"])
                if matched and not found:
                    reciprocal_rank += 1 / position
                found.update(matched)
            hits += bool(found)
            full_answers += gold <= found
            total_recall += len(found) / len(gold)
        count = len(queries)
        report[strategy] = {
            "questions": count,
            "chunks": len(chunks),
            f"hit_at_{top_k}": round(hits / count, 4),
            f"evidence_recall_at_{top_k}": round(total_recall / count, 4),
            f"full_answer_at_{top_k}": round(full_answers / count, 4),
            f"mrr_at_{top_k}": round(reciprocal_rank / count, 4),
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="转换后的 val 或 test 目录")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k 必须大于 0")
    print(json.dumps(evaluate(args.dataset, args.top_k), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
