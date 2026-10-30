"""Check the LLM judge's correctness verdicts against human grades.

    python -m evals.agreement export baseline baseline-run2 no-similarity-gate no-similarity-gate-run2
    # grade evals/human_grades/sample.csv by hand (fill in human_verdict)
    python -m evals.agreement score

Export pools the unique (question, answer) pairs from the given runs and writes
a blind grading sheet: the judge's verdicts go to a separate key file. Every
answer the judge did not mark correct is included, plus a seeded random sample
of the ones it did, because a sample drawn at random would be almost all
"correct" and agreement on it would say little. Score prints a confusion
matrix, raw agreement, and Cohen's kappa.
"""

import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from evals.run import NO_RESULTS_ANSWER

EVALS_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVALS_DIR / "results"
DATASET = EVALS_DIR / "dataset.jsonl"
GRADES_DIR = EVALS_DIR / "human_grades"
SHEET = GRADES_DIR / "sample.csv"
KEY = GRADES_DIR / "key.json"

VERDICTS = ("correct", "partial", "incorrect")
SAMPLE_SIZE = 40
SEED = 20261030
SHEET_COLUMNS = [
    "sample_id",
    "question",
    "reference_answer",
    "answer",
    "human_verdict",
    "notes",
]


def pool_answers(runs: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Unique (question id, answer) pairs across runs, with the judge's verdict.

    Identical answers in different runs get one entry. If the judge graded the
    same answer differently across runs, the entry is dropped: there is no
    single judge verdict to compare against.
    """
    pooled: dict[tuple[str, str], dict[str, Any]] = {}
    for label, records in runs.items():
        for record in records:
            answer = record["answer"].strip()
            verdict = record["correctness"]["verdict"]
            entry = pooled.setdefault(
                (record["id"], answer),
                {"id": record["id"], "answer": answer, "verdicts": set(), "runs": []},
            )
            entry["verdicts"].add(verdict)
            entry["runs"].append(label)
    return [
        {
            "id": e["id"],
            "answer": e["answer"],
            "judge_verdict": next(iter(e["verdicts"])),
            "runs": e["runs"],
        }
        for e in pooled.values()
        if len(e["verdicts"]) == 1
    ]


def select_sample(
    pool: list[dict[str, Any]], size: int, seed: int
) -> list[dict[str, Any]]:
    """Every non-correct answer, topped up with random correct ones, shuffled."""
    flagged = [p for p in pool if p["judge_verdict"] != "correct"]
    correct = [p for p in pool if p["judge_verdict"] == "correct"]
    rng = random.Random(seed)  # nosec B311 - reproducible sampling, not security
    top_up = rng.sample(correct, min(len(correct), max(0, size - len(flagged))))
    sample = flagged + top_up
    rng.shuffle(sample)
    return sample


def confusion_matrix(
    pairs: list[tuple[str, str]],
) -> dict[str, dict[str, int]]:
    """Counts keyed [human][judge]."""
    counts = Counter(pairs)
    return {h: {j: counts[(h, j)] for j in VERDICTS} for h in VERDICTS}


def raw_agreement(pairs: list[tuple[str, str]]) -> float:
    return sum(1 for h, j in pairs if h == j) / len(pairs)


def cohens_kappa(pairs: list[tuple[str, str]]) -> float:
    """Agreement corrected for what the two graders' label rates predict by chance."""
    n = len(pairs)
    observed = raw_agreement(pairs)
    human = Counter(h for h, _ in pairs)
    judge = Counter(j for _, j in pairs)
    expected = sum(human[v] * judge[v] for v in VERDICTS) / (n * n)
    if expected == 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def format_report(pairs: list[tuple[str, str]]) -> str:
    matrix = confusion_matrix(pairs)
    lines = [
        f"Graded: {len(pairs)}",
        f"Raw agreement: {raw_agreement(pairs):.0%}",
        f"Cohen's kappa: {cohens_kappa(pairs):.2f}",
        "",
        "| Human \\ Judge | " + " | ".join(VERDICTS) + " |",
        "|---|" + "---|" * len(VERDICTS),
    ]
    for h in VERDICTS:
        lines.append(
            f"| {h} | " + " | ".join(str(matrix[h][j]) for j in VERDICTS) + " |"
        )
    return "\n".join(lines)


def load_dataset() -> dict[str, dict[str, Any]]:
    rows = [json.loads(line) for line in DATASET.read_text().splitlines() if line]
    return {row["id"]: row for row in rows}


def export(labels: list[str]) -> None:
    if SHEET.exists():
        with SHEET.open(newline="") as f:
            if any(row["human_verdict"].strip() for row in csv.DictReader(f)):
                raise SystemExit(
                    f"{SHEET.relative_to(EVALS_DIR.parent)} already has grades. "
                    "Move it aside before exporting a new sheet."
                )
    runs = {
        label: json.loads((RESULTS_DIR / f"{label}.json").read_text())["records"]
        for label in labels
    }
    pool = pool_answers(runs)
    sample = select_sample(pool, SAMPLE_SIZE, SEED)
    dataset = load_dataset()

    GRADES_DIR.mkdir(exist_ok=True)
    key = {}
    with SHEET.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SHEET_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for n, entry in enumerate(sample, start=1):
            sample_id = f"s{n:02d}"
            question = dataset[entry["id"]]
            writer.writerow(
                {
                    "sample_id": sample_id,
                    "question": question["question"],
                    "reference_answer": question["expected_answer"],
                    "answer": entry["answer"],
                    "human_verdict": "",
                    "notes": "",
                }
            )
            key[sample_id] = {
                "question_id": entry["id"],
                "judge_verdict": entry["judge_verdict"],
                "runs": entry["runs"],
            }
    KEY.write_text(json.dumps(key, indent=2) + "\n")
    flagged = sum(1 for e in sample if e["judge_verdict"] != "correct")
    print(
        f"Wrote {len(sample)} answers to {SHEET.relative_to(EVALS_DIR.parent)} "
        f"({flagged} the judge did not mark correct, from {len(pool)} unique)."
    )


def graded_pairs(
    rows: list[dict[str, str]],
    key: dict[str, dict[str, Any]],
    skip_answer: str | None = None,
) -> list[tuple[str, str]]:
    """(human, judge) verdicts for graded rows, optionally skipping one answer text."""
    pairs = []
    for row in rows:
        human = row["human_verdict"].strip().lower()
        if not human or (skip_answer and row["answer"].strip() == skip_answer):
            continue
        if human not in VERDICTS:
            raise ValueError(f"{row['sample_id']}: unknown verdict {human!r}")
        pairs.append((human, key[row["sample_id"]]["judge_verdict"]))
    return pairs


def score() -> None:
    key = json.loads(KEY.read_text())
    with SHEET.open(newline="") as f:
        rows = list(csv.DictReader(f))
    pairs = graded_pairs(rows, key)
    if not pairs:
        raise SystemExit("No graded rows yet. Fill in human_verdict in the sheet.")
    print(format_report(pairs))
    # The app's canned no-results reply is trivially incorrect, so it inflates
    # agreement. Report the answers that needed judgment on their own too.
    judged = graded_pairs(rows, key, skip_answer=NO_RESULTS_ANSWER)
    print("\nExcluding the app's no-results reply:\n")
    print(format_report(judged))


def main() -> None:
    command, *labels = sys.argv[1:] or [""]
    if command == "export" and labels:
        export(labels)
    elif command == "score":
        score()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
