"""Tests for the judge-vs-human agreement helpers in evals/agreement.py."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.agreement import (  # noqa: E402
    cohens_kappa,
    confusion_matrix,
    graded_pairs,
    pool_answers,
    raw_agreement,
    select_sample,
)


def record(qid: str, answer: str, verdict: str) -> dict:
    return {"id": qid, "answer": answer, "correctness": {"verdict": verdict}}


class TestPoolAnswers:
    def test_merges_identical_answers_across_runs(self):
        pool = pool_answers(
            {
                "run1": [record("q1", "Three feet.", "correct")],
                "run2": [record("q1", "Three feet.\n", "correct")],
            }
        )
        assert pool == [
            {
                "id": "q1",
                "answer": "Three feet.",
                "judge_verdict": "correct",
                "runs": ["run1", "run2"],
            }
        ]

    def test_same_answer_to_different_questions_stays_separate(self):
        pool = pool_answers(
            {
                "run1": [
                    record("q1", "Not found.", "incorrect"),
                    record("q2", "Not found.", "incorrect"),
                ]
            }
        )
        assert [p["id"] for p in pool] == ["q1", "q2"]

    def test_drops_answers_the_judge_graded_inconsistently(self):
        pool = pool_answers(
            {
                "run1": [record("q1", "Maybe.", "partial")],
                "run2": [record("q1", "Maybe.", "correct")],
            }
        )
        assert pool == []


class TestSelectSample:
    def make_pool(self, correct: int, flagged: int) -> list[dict]:
        return [{"id": f"c{i}", "judge_verdict": "correct"} for i in range(correct)] + [
            {"id": f"f{i}", "judge_verdict": "partial"} for i in range(flagged)
        ]

    def test_keeps_every_flagged_answer_and_tops_up_with_correct(self):
        sample = select_sample(self.make_pool(correct=50, flagged=5), 20, seed=1)
        ids = {s["id"] for s in sample}
        assert len(sample) == 20
        assert {f"f{i}" for i in range(5)} <= ids

    def test_is_deterministic_for_a_seed(self):
        pool = self.make_pool(correct=50, flagged=5)
        assert select_sample(pool, 20, seed=1) == select_sample(pool, 20, seed=1)

    def test_flagged_beyond_size_are_all_kept(self):
        sample = select_sample(self.make_pool(correct=10, flagged=8), 5, seed=1)
        assert len(sample) == 8


class TestAgreementStats:
    def test_perfect_agreement(self):
        pairs = [("correct", "correct"), ("incorrect", "incorrect")]
        assert raw_agreement(pairs) == 1.0
        assert cohens_kappa(pairs) == 1.0

    def test_kappa_discounts_agreement_on_a_lopsided_label(self):
        # 9 of 10 agree, but both graders say "correct" almost every time,
        # so most of that agreement is expected by chance.
        pairs = [("correct", "correct")] * 9 + [("partial", "correct")]
        assert raw_agreement(pairs) == 0.9
        assert cohens_kappa(pairs) == pytest.approx(0.0)

    def test_kappa_known_value(self):
        # p_o = 0.7; human 6 correct / 4 incorrect, judge 5 / 5 -> p_e = 0.5
        pairs = (
            [("correct", "correct")] * 4
            + [("incorrect", "incorrect")] * 3
            + [("correct", "incorrect")] * 2
            + [("incorrect", "correct")]
        )
        assert cohens_kappa(pairs) == pytest.approx(0.4)

    def test_confusion_matrix_is_keyed_human_then_judge(self):
        matrix = confusion_matrix([("partial", "correct"), ("partial", "correct")])
        assert matrix["partial"]["correct"] == 2
        assert matrix["correct"]["partial"] == 0


class TestGradedPairs:
    KEY = {"s01": {"judge_verdict": "correct"}, "s02": {"judge_verdict": "incorrect"}}

    def row(self, sample_id: str, verdict: str, answer: str = "An answer.") -> dict:
        return {"sample_id": sample_id, "human_verdict": verdict, "answer": answer}

    def test_skips_ungraded_rows_and_normalizes_case(self):
        rows = [self.row("s01", " Correct "), self.row("s02", "")]
        assert graded_pairs(rows, self.KEY) == [("correct", "correct")]

    def test_skips_a_given_answer_text(self):
        rows = [
            self.row("s01", "correct"),
            self.row("s02", "incorrect", "Not found.\n"),
        ]
        assert graded_pairs(rows, self.KEY, skip_answer="Not found.") == [
            ("correct", "correct")
        ]

    def test_rejects_unknown_verdicts(self):
        with pytest.raises(ValueError, match="s01"):
            graded_pairs([self.row("s01", "mostly right")], self.KEY)
