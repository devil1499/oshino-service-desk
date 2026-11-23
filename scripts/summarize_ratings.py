"""汇总人工评分；不代替人工评判。"""

import argparse
import csv
import json
import statistics
from pathlib import Path


def summarize(path: Path) -> dict:
    dimensions = ["relevance", "correctness", "usability"]
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != ["sample_id", "run_id", "rater", *dimensions]:
            raise ValueError("评分表头与模板不一致")
        rows = list(reader)
    if not rows:
        raise ValueError("评分表为空；请人工填写后再运行")
    keys = set()
    for number, row in enumerate(rows, start=1):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"第{number}条评分列数不正确")
        if (
            not row["sample_id"].strip()
            or not row["rater"].strip()
            or int(row["run_id"]) <= 0
        ):
            raise ValueError(f"第{number}条评分缺少样本、有效生成记录ID或评分人")
        key = (row["sample_id"], row["run_id"], row["rater"])
        if key in keys:
            raise ValueError(f"第{number}条为同一评分人的重复评分")
        keys.add(key)
        for field in dimensions:
            row[field] = int(row[field])
            if not 1 <= row[field] <= 5:
                raise ValueError(f"第{number}条的{field}必须为1—5整数")
    means = {field: statistics.mean(row[field] for row in rows) for field in dimensions}
    return {
        "ratings": len(rows),
        "samples": len({row["sample_id"] for row in rows}),
        "raters": len({row["rater"] for row in rows}),
        "means": means,
        "overall_mean": statistics.mean(means.values()),
    }


def main():
    parser = argparse.ArgumentParser(description="人工评分统计")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = summarize(args.input)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    print(f"已保存：{args.output}")


if __name__ == "__main__":
    main()
