"""Tests for the eval scoring functions in evals/metrics.py and evals/judge.py."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.judge import (  # noqa: E402
    faithfulness_score,
    parse_json_object,
    parse_verdict,
)
from evals.metrics import (  # noqa: E402
    RetrievedChunk,
    chunk_matches,
    citations_valid,
    cited_numbers,
    first_hit_rank,
    hit_rate,
    mean_reciprocal_rank,
    normalize,
    passage_coverage,
    passage_recall,
)

DOC = "handbook.pdf"


class TestNormalize:
    def test_folds_ligatures_quotes_and_spacing(self):
        assert normalize("ﬂexible  time oﬀ,\n “approved”") == [
            "flexible",
            "time",
            "off",
            "approved",
        ]

    def test_empty(self):
        assert normalize("  ...  ") == []


class TestPassageCoverage:
    def test_full_match_ignores_formatting(self):
        chunk = "Rub your hands\ntogether for a minimum of 20 seconds; lather..."
        assert (
            passage_coverage(
                "rub your hands together for a minimum of 20 seconds", chunk
            )
            == 1.0
        )

    def test_passage_split_across_chunks_counts_longest_run(self):
        chunk = "...end of page. Employees accrue one hour of paid sick"
        coverage = passage_coverage(
            "Employees accrue one hour of paid sick leave for every 30 hours", chunk
        )
        assert coverage == pytest.approx(7 / 12)

    def test_word_boundaries_respected(self):
        assert passage_coverage("art", "the start of the day") == 0.0

    def test_empty_passage(self):
        assert passage_coverage("", "anything") == 0.0


class TestChunkMatches:
    def test_requires_expected_document(self):
        chunk = RetrievedChunk(
            "other.pdf", "Vacation days are granted only on a full-day basis."
        )
        assert not chunk_matches(
            chunk, DOC, "Vacation days are granted only on a full-day basis."
        )

    def test_any_document_when_source_unknown(self):
        chunk = RetrievedChunk(
            "other.pdf", "Vacation days are granted only on a full-day basis."
        )
        assert chunk_matches(chunk, None, "vacation days are granted only")

    def test_below_coverage_threshold(self):
        chunk = RetrievedChunk(DOC, "granted only on")
        assert not chunk_matches(
            chunk, DOC, "Vacation days are granted only on a full-day basis"
        )


class TestRanking:
    chunks = [
        RetrievedChunk(DOC, "unrelated text about parking"),
        RetrievedChunk("other.pdf", "the late charge applies after ten days"),
        RetrievedChunk(DOC, "the late charge applies after ten days"),
    ]

    def test_first_hit_rank_skips_wrong_document(self):
        assert (
            first_hit_rank(self.chunks, DOC, ["late charge applies after ten days"])
            == 3
        )

    def test_first_hit_rank_none_when_missing(self):
        assert first_hit_rank(self.chunks, DOC, ["security deposit"]) is None

    def test_passage_recall_counts_each_passage(self):
        passages = ["late charge applies after ten days", "security deposit is due"]
        assert passage_recall(self.chunks, DOC, passages) == 0.5

    def test_passage_recall_no_passages(self):
        assert passage_recall(self.chunks, DOC, []) == 0.0


class TestAggregates:
    def test_hit_rate(self):
        assert hit_rate([1, 3, None, 6], k=5) == 0.5

    def test_mrr_counts_misses_as_zero(self):
        assert mean_reciprocal_rank([1, 2, None, 4]) == pytest.approx(
            (1 + 0.5 + 0 + 0.25) / 4
        )

    def test_empty_inputs(self):
        assert hit_rate([], k=5) is None
        assert mean_reciprocal_rank([]) is None


class TestCitations:
    def test_cited_numbers_handles_groups(self):
        assert cited_numbers("Yes [1]. Also [2, 3] and [10].") == [1, 2, 3, 10]

    def test_ignores_non_citation_brackets(self):
        assert cited_numbers("Pay [ORGANIZATION] staff [or 60] minutes") == []

    def test_valid_when_all_within_context(self):
        assert citations_valid("A [1] B [3]", context_size=3)

    def test_invalid_when_out_of_range(self):
        assert not citations_valid("A [4]", context_size=3)
        assert not citations_valid("A [0]", context_size=3)

    def test_no_citations_is_valid(self):
        assert citations_valid("No citations here.", context_size=0)


class TestJudgeParsing:
    def test_parse_json_inside_code_fence(self):
        assert parse_json_object('```json\n{"verdict": "correct"}\n```') == {
            "verdict": "correct"
        }

    def test_parse_json_missing(self):
        with pytest.raises(ValueError):
            parse_json_object("no json here")

    def test_faithfulness_score(self):
        parsed = {
            "claims": [{"supported": True}, {"supported": False}, {"supported": True}]
        }
        assert faithfulness_score(parsed) == pytest.approx(2 / 3)

    def test_faithfulness_none_without_claims(self):
        assert faithfulness_score({"claims": []}) is None

    def test_verdict_validation(self):
        assert parse_verdict({"verdict": "partial"}) == "partial"
        with pytest.raises(ValueError):
            parse_verdict({"verdict": "mostly"})
