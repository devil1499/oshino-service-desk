"""把本机 CSDS 三个原始 JSON 转成独立的分析与切分实验 JSONL。"""

import argparse
import hashlib
import json
import re
from contextlib import ExitStack
from pathlib import Path


SPLITS = ("train", "val", "test")
CHARACTER_LIMIT = 500
CHARACTER_OVERLAP = 80


def clean_utterance(value: str) -> str:
    # CSDS 的 utterance 已按词插入空格；去掉汉字间空格，保留英文词之间的空格。
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value.strip())
    return re.sub(r"\s*([，。！？；：,.!?;:])\s*", r"\1", text)


def document_from_dialogue(row: dict, split: str) -> dict:
    document_id = f"csds-{split}-{row['DialogueID']}"
    parts = []
    utterances = []
    offset = 0
    for index, item in enumerate(row["Dialogue"]):
        if item["turn"] != index:
            raise ValueError(f"{document_id} 的 turn 与话语位置不一致")
        role = {"Q": "用户", "A": "客服"}[item["speaker"]]
        prefix = f"[{index}] {role}："
        content = clean_utterance(item["utterance"])
        line = prefix + content + "\n"
        utterances.append({"id": index, "role": role, "text": content,
                           "line_start": offset, "line_end": offset + len(line),
                           "start": offset + len(prefix), "end": offset + len(prefix) + len(content)})
        parts.append(line)
        offset += len(line)
    return {"document_id": document_id, "source_dialogue_id": row["DialogueID"],
            "text": "".join(parts), "utterances": utterances}


def chunk_ranges(document: dict, strategy: str):
    text = document["text"]
    if strategy == "fixed-500-80":
        start = 0
        while start < len(text):
            end = min(start + CHARACTER_LIMIT, len(text))
            yield start, end
            if end == len(text):
                break
            start += CHARACTER_LIMIT - CHARACTER_OVERLAP
        return

    group_start = None
    group_end = 0
    for utterance in document["utterances"]:
        start, end = utterance["line_start"], utterance["line_end"]
        if group_start is not None and end - group_start > CHARACTER_LIMIT:
            yield group_start, group_end
            group_start = None
        if end - start > CHARACTER_LIMIT:
            part_start = start
            while part_start < end:
                part_end = min(part_start + CHARACTER_LIMIT, end)
                yield part_start, part_end
                if part_end == end:
                    break
                part_start += CHARACTER_LIMIT - CHARACTER_OVERLAP
            group_end = 0
            continue
        if group_start is None:
            group_start = start
        group_end = end
    if group_start is not None:
        yield group_start, group_end


def chunks_for(document: dict, strategy: str):
    for number, (start, end) in enumerate(chunk_ranges(document, strategy), 1):
        overlaps = [item["id"] for item in document["utterances"]
                    if item["start"] < end and item["end"] > start]
        complete = [item["id"] for item in document["utterances"]
                    if start <= item["start"] and item["end"] <= end]
        yield {"chunk_id": f"{document['document_id']}-{strategy}-{number:03d}",
               "document_id": document["document_id"], "strategy": strategy,
               "text": document["text"][start:end], "start": start, "end": end,
               "utterance_ids": overlaps, "complete_utterance_ids": complete}


def write_jsonl(handle, item: dict):
    handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def convert_split(source: Path, destination: Path, split: str) -> dict:
    source_bytes = source.read_bytes()
    dialogues = json.loads(source_bytes)
    if not isinstance(dialogues, list):
        raise ValueError(f"{source} 须为对话列表")
    destination.mkdir(parents=True, exist_ok=True)
    counts = {"dialogues": 0, "analysis_samples": 0, "retrieval_questions": 0,
              "chunks_fixed_500_80": 0, "chunks_dialogue_turns": 0}
    filenames = ("documents.jsonl", "analysis.jsonl", "queries.jsonl", "answers.jsonl",
                 "chunks-fixed-500-80.jsonl", "chunks-dialogue-turns.jsonl")
    with ExitStack() as stack:
        outputs = {name: stack.enter_context((destination / name).open("w", encoding="utf-8"))
                   for name in filenames}
        for row in dialogues:
            document = document_from_dialogue(row, split)
            write_jsonl(outputs["documents.jsonl"], document)
            counts["dialogues"] += 1
            for strategy, filename, counter in (
                ("fixed-500-80", "chunks-fixed-500-80.jsonl", "chunks_fixed_500_80"),
                ("dialogue-turns", "chunks-dialogue-turns.jsonl", "chunks_dialogue_turns"),
            ):
                for chunk in chunks_for(document, strategy):
                    write_jsonl(outputs[filename], chunk)
                    counts[counter] += 1
            utterances = document["utterances"]
            for index, qa in enumerate(row["QA"], 1):
                question_ids = qa["QueSummUttIDs"]
                answer_ids = qa["AnsSummLongUttIDs"]
                if any(not isinstance(item, int) or item < 0 or item >= len(utterances)
                       for item in question_ids + answer_ids):
                    raise ValueError(f"{document['document_id']} 的 QA {index} 引用了不存在的话语")
                sample_id = f"{document['document_id']}-q{index:02d}"
                user_input = "\n".join(utterances[item]["text"] for item in question_ids)
                reference = qa["QueSumm"].strip()
                if not user_input or not reference:
                    raise ValueError(f"{sample_id} 缺少用户输入或参考摘要")
                write_jsonl(outputs["analysis.jsonl"], {
                    "sample_id": sample_id, "document_id": document["document_id"],
                    "input": {"text": user_input, "utterance_ids": question_ids},
                    "reference": {"summary": reference, "source_intent": qa.get("intent") or None,
                                  "category_id": None, "priority": None},
                })
                counts["analysis_samples"] += 1
                if not answer_ids:
                    continue
                write_jsonl(outputs["queries.jsonl"], {
                    "query_id": sample_id, "document_id": document["document_id"],
                    "query": reference, "question": f"{reference}客服应如何回复？",
                })
                write_jsonl(outputs["answers.jsonl"], {
                    "query_id": sample_id, "document_id": document["document_id"],
                    "reference_answer": qa["AnsSummLong"].strip(),
                    "relevant_utterance_ids": list(dict.fromkeys(answer_ids)),
                })
                counts["retrieval_questions"] += 1
    return {"source_sha256": hashlib.sha256(source_bytes).hexdigest(), **counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="含 train/val/test.json 的原始目录")
    parser.add_argument("--output", type=Path, required=True, help="项目内独立的实验数据目录")
    args = parser.parse_args()
    manifest = {split: convert_split(args.source / f"{split}.json", args.output / split, split)
                for split in SPLITS}
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                                 encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
