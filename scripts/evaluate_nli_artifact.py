"""Block resource-v4 rollout unless an NLI artifact meets calibration gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--predictions",
        required=True,
        help="JSONL rows with gold and predicted labels.",
    )
    parser.add_argument("--artifact-digest", required=True)
    return parser.parse_args()


def _safe_div(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def evaluate(path: Path) -> dict[str, float | int]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    fact_tp = fact_fp = fact_fn = 0
    contradiction_total = contradiction_recalled = 0
    for row in rows:
        gold = str(row.get("gold") or "")
        predicted = str(row.get("predicted") or "")
        if predicted == "entailment" and gold == "entailment":
            fact_tp += 1
        elif predicted == "entailment":
            fact_fp += 1
        elif gold == "entailment":
            fact_fn += 1
        if gold == "contradiction":
            contradiction_total += 1
            contradiction_recalled += predicted == "contradiction"
    precision = _safe_div(fact_tp, fact_tp + fact_fp)
    recall = _safe_div(fact_tp, fact_tp + fact_fn)
    fact_f1 = _safe_div(2 * precision * recall, precision + recall)
    contradiction_recall = _safe_div(
        contradiction_recalled,
        contradiction_total,
    )
    return {
        "samples": len(rows),
        "fact_f1": round(fact_f1, 6),
        "contradiction_recall": round(contradiction_recall, 6),
    }


def main() -> int:
    args = parse_args()
    if not args.artifact_digest.startswith("sha256:"):
        raise SystemExit("artifact digest must be immutable and start with sha256:")
    result = evaluate(Path(args.predictions))
    result["artifact_digest"] = args.artifact_digest
    print(json.dumps(result, sort_keys=True))
    if result["fact_f1"] < 0.90:
        return 2
    if result["contradiction_recall"] < 0.95:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
