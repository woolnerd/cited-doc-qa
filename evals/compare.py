"""Print a markdown table comparing eval runs.

    python -m evals.compare baseline baseline-run2 no-similarity-gate no-similarity-gate-run2
"""

import json
import sys
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).resolve().parent / "results"

ROWS = [
    (
        "Questions with any candidates containing the answer",
        "candidate_hit_rate",
        "pct",
    ),
    ("Answer passage in final context (hit@5)", "context_hit_at_5", "pct"),
    ("Answer passage ranked first (hit@1)", "context_hit_at_1", "pct"),
    ("MRR of answer passage", "context_mrr", "num"),
    ("Full-text search returned nothing", "fulltext_zero_result_rate", "pct"),
    ("Answers judged correct", "answer_correct", "pct"),
    ("Answers judged partial", "answer_partial", "pct"),
    ("Answers judged incorrect", "answer_incorrect", "pct"),
    ("Mean faithfulness (supported claims / claims)", "faithfulness_mean", "num"),
    ("Answers with every claim supported", "fully_faithful_rate", "pct"),
    (
        "Answers whose citations all point at real context",
        "citations_valid_rate",
        "pct",
    ),
]


def format_value(value: Any, kind: str) -> str:
    if value is None:
        return "n/a"
    return f"{value:.0%}" if kind == "pct" else f"{value:.2f}"


def table(runs: list[dict[str, Any]]) -> str:
    header = "| Metric | " + " | ".join(r["label"] for r in runs) + " |"
    divider = "|---|" + "---|" * len(runs)
    lines = [header, divider]
    for name, key, kind in ROWS:
        cells = [format_value(r["summary"].get(key), kind) for r in runs]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    labels = sys.argv[1:]
    if not labels:
        raise SystemExit(__doc__)
    runs = [json.loads((RESULTS_DIR / f"{label}.json").read_text()) for label in labels]
    print(table(runs))


if __name__ == "__main__":
    main()
