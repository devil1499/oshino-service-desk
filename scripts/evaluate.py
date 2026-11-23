"""对已有独立评测工单调用真实API；从工程根目录运行。"""

import argparse
import getpass
import hashlib
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    ValidationError,
    model_validator,
)


class Sample(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    sample_id: str = Field(min_length=1)
    ticket_id: StrictInt = Field(gt=0)
    relevant_case_ids: list[StrictInt] = Field(min_length=1)
    relevant_document_ids: list[StrictInt]
    expected_category_id: StrictInt = Field(gt=0)
    expected_priority: Literal["P1", "P2", "P3", "P4"]

    @model_validator(mode="after")
    def unique_labels(self):
        if self.ticket_id in self.relevant_case_ids:
            raise ValueError("当前工单不得标成自身参考案例")
        for values in [self.relevant_case_ids, self.relevant_document_ids]:
            if len(values) != len(set(values)) or any(value <= 0 for value in values):
                raise ValueError("相关ID必须大于0且不能重复")
        return self


class LoginResponse(BaseModel):
    access_token: str = Field(min_length=1)


class CaseHit(BaseModel):
    id: StrictInt


class CaseResult(BaseModel):
    items: list[CaseHit] = Field(max_length=5)


class DocumentHit(BaseModel):
    document_id: StrictInt


class KnowledgeResult(BaseModel):
    items: list[DocumentHit] = Field(max_length=5)


class DraftResult(BaseModel):
    category_id: StrictInt
    priority: Literal["P1", "P2", "P3", "P4"]


class GenerationResult(BaseModel):
    id: StrictInt
    draft: DraftResult
    model: str
    prompt_version: str
    duration_ms: StrictInt


def recall_at_five(predicted: list[int], relevant: list[int]) -> float:
    return len(set(predicted[:5]) & set(relevant)) / len(set(relevant))


def macro_f1(expected: list[int], predicted: list[int]) -> float:
    scores = []
    for category in sorted(set(expected) | set(predicted)):
        true_positive = sum(
            a == category and b == category
            for a, b in zip(expected, predicted, strict=True)
        )
        false_positive = sum(
            a != category and b == category
            for a, b in zip(expected, predicted, strict=True)
        )
        false_negative = sum(
            a == category and b != category
            for a, b in zip(expected, predicted, strict=True)
        )
        scores.append(
            2 * true_positive / (2 * true_positive + false_positive + false_negative)
        )
    return statistics.mean(scores)


def load_samples(path: Path) -> list[Sample]:
    samples = [
        Sample.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not samples:
        raise ValueError("评测集为空，请先人工标注")
    if len({sample.sample_id for sample in samples}) != len(samples) or len(
        {sample.ticket_id for sample in samples}
    ) != len(samples):
        raise ValueError("sample_id 与 ticket_id 均不得重复")
    return samples


def main():
    parser = argparse.ArgumentParser(
        description="独立评测；仅 --generate 会产生新的AI生成记录和模型费用"
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api")
    parser.add_argument("--mode", choices=["bm25", "dense", "hybrid"], default="hybrid")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="额外调用完整双源混合检索+重排+生成；不受--mode影响",
    )
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise SystemExit("base-url 必须是无账号、密码或查询参数的HTTP(S) API地址")
    try:
        samples = load_samples(args.dataset)
    except (ValidationError, ValueError) as error:
        raise SystemExit(f"评测集不合格：{error}") from None
    if args.output.exists():
        raise SystemExit("结果文件已存在，请使用新的文件名")
    username = input("登录用户名：").strip()
    password = getpass.getpass("登录密码（不回显）：")
    report = {
        "status": "running",
        "created_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "case_mode": args.mode,
        "generate": args.generate,
        "generation_pipeline": "dual-source-hybrid-rerank-v1"
        if args.generate
        else None,
        "api_base_url": args.base_url,
        "details": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # 每条完成即保存；中途失败会留下 failed 状态，不计算假成功的均值。
    with (
        args.output.open("x", encoding="utf-8") as output,
        httpx.Client(timeout=180.0) as client,
    ):

        def save_report():
            output.seek(0)
            json.dump(report, output, ensure_ascii=False, indent=2)
            output.truncate()
            output.flush()

        def post(path, body=None):
            response = client.post(args.base_url.rstrip("/") + path, json=body)
            response.raise_for_status()
            return response.json()

        try:
            login = LoginResponse.model_validate(
                post("/auth/login", {"username": username, "password": password})
            )
            password = ""
            client.headers["Authorization"] = "Bearer " + login.access_token
            config = client.get(args.base_url.rstrip("/") + "/evaluation/config")
            config.raise_for_status()
            report["configuration"] = config.json()
            for sample in samples:
                started = time.monotonic()
                result = CaseResult.model_validate(
                    post(f"/tickets/{sample.ticket_id}/similar?mode={args.mode}")
                )
                knowledge = KnowledgeResult.model_validate(
                    post(f"/tickets/{sample.ticket_id}/knowledge")
                )
                predicted = [hit.id for hit in result.items]
                documents = list(
                    dict.fromkeys(hit.document_id for hit in knowledge.items)
                )
                item = {
                    "sample_id": sample.sample_id,
                    "ticket_id": sample.ticket_id,
                    "case_ids": predicted,
                    "document_ids": documents,
                    "case_recall_at_5": recall_at_five(
                        predicted, sample.relevant_case_ids
                    ),
                    "knowledge_recall_from_top5_chunks": recall_at_five(
                        documents, sample.relevant_document_ids
                    )
                    if sample.relevant_document_ids
                    else None,
                    "retrieval_pair_ms": round((time.monotonic() - started) * 1000),
                }
                if args.generate:
                    wall_started = time.monotonic()
                    generated = GenerationResult.model_validate(
                        post(f"/tickets/{sample.ticket_id}/assist")
                    )
                    item.update(
                        run_id=generated.id,
                        expected_category_id=sample.expected_category_id,
                        predicted_category_id=generated.draft.category_id,
                        expected_priority=sample.expected_priority,
                        predicted_priority=generated.draft.priority,
                        model=generated.model,
                        prompt_version=generated.prompt_version,
                        generation_server_ms=generated.duration_ms,
                        generation_wall_ms=round(
                            (time.monotonic() - wall_started) * 1000
                        ),
                    )
                report["details"].append(item)
                save_report()
                print(
                    f"已完成 {len(report['details'])}/{len(samples)}：{sample.sample_id}",
                    flush=True,
                )
        except (httpx.HTTPError, ValidationError, ValueError) as error:
            report["status"] = "failed"
            report["error"] = (
                f"HTTP {error.response.status_code}"
                if isinstance(error, httpx.HTTPStatusError)
                else type(error).__name__
            )
            save_report()
            raise SystemExit(
                f"评测中止，未汇总指标；检查后端与数据。记录：{args.output}"
            ) from None
        details = report["details"]
        labeled_knowledge = [
            item["knowledge_recall_from_top5_chunks"]
            for item in details
            if item["knowledge_recall_from_top5_chunks"] is not None
        ]
        report["metrics"] = {
            "count": len(details),
            "mean_case_recall_at_5": statistics.mean(
                item["case_recall_at_5"] for item in details
            ),
            "knowledge_labeled_count": len(labeled_knowledge),
            "mean_knowledge_recall_from_top5_chunks": statistics.mean(labeled_knowledge)
            if labeled_knowledge
            else None,
        }
        if args.generate:
            report["metrics"].update(
                category_macro_f1=macro_f1(
                    [item["expected_category_id"] for item in details],
                    [item["predicted_category_id"] for item in details],
                ),
                priority_accuracy=statistics.mean(
                    item["expected_priority"] == item["predicted_priority"]
                    for item in details
                ),
                mean_generation_wall_ms=statistics.mean(
                    item["generation_wall_ms"] for item in details
                ),
            )
        report["status"] = "completed"
        save_report()
    print(f"评测完成：{args.output}")


if __name__ == "__main__":
    main()
