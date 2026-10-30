"""Tests for the retrieval gate's replay and comparison logic (evals/replay.py, evals/gate.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.gate import rank_changes, regressions  # noqa: E402
from evals.replay import (  # noqa: E402
    Recording,
    ReplayMiss,
    decode_vector,
    encode_vector,
    pair_key,
    rank_by_score,
    text_key,
)

SUMMARY = {
    "candidate_hit_rate": 1.0,
    "candidate_mrr": 0.8,
    "context_hit_at_1": 0.85,
    "context_hit_at_5": 1.0,
    "context_mrr": 0.9,
    "context_recall": 1.0,
    "fulltext_zero_result_rate": 0.0,
    "vector_zero_result_rate": 0.0,
    "other_session_chunks": 0,
}


def test_vector_round_trip_keeps_float16_precision():
    vector = [0.0123, -0.5, 0.99, 0.0]
    decoded = decode_vector(encode_vector(vector))
    assert decoded == pytest.approx(vector, abs=1e-3)


def test_pair_key_depends_on_query_and_document():
    assert pair_key("q", "doc") != pair_key("q", "doc2")
    assert pair_key("q", "doc") != pair_key("q2", "doc")
    # The separator keeps ("ab", "c") and ("a", "bc") apart.
    assert pair_key("ab", "c") != pair_key("a", "bc")


def test_rank_by_score_orders_best_first_and_breaks_ties_by_index():
    assert rank_by_score([0.2, 0.9, 0.2, 0.5], top_n=3) == [
        (1, 0.9),
        (3, 0.5),
        (0, 0.2),
    ]


def test_recording_serves_recorded_values():
    recording = Recording("embed-model", "rerank-model")
    recording.embeddings[text_key("hello")] = encode_vector([0.5, 0.25])
    recording.rerank_scores[pair_key("q", "d")] = 0.7

    assert recording.embedding("hello") == [0.5, 0.25]
    assert recording.rerank_score("q", "d") == 0.7
    assert recording.misses == []


def test_recording_tracks_misses():
    """The reranker swallows exceptions and falls back to RRF, so a miss must
    be recorded where the gate can see it, not only raised."""
    recording = Recording("embed-model", "rerank-model")

    with pytest.raises(ReplayMiss):
        recording.embedding("unseen text")
    with pytest.raises(ReplayMiss):
        recording.rerank_score("q", "unseen chunk")

    assert len(recording.misses) == 2


def test_recording_save_and_load(tmp_path):
    recording = Recording("embed-model", "rerank-model")
    recording.embeddings[text_key("a")] = encode_vector([1.0])
    recording.rerank_scores[pair_key("q", "a")] = 0.3
    path = tmp_path / "recording.json"

    recording.save(path)
    loaded = Recording.load(path)

    assert loaded.embedding_model == "embed-model"
    assert loaded.rerank_model == "rerank-model"
    assert loaded.embedding("a") == [1.0]
    assert loaded.rerank_score("q", "a") == 0.3


def test_no_regression_when_unchanged():
    assert regressions(SUMMARY, dict(SUMMARY)) == []


def test_improvement_is_not_a_regression():
    better = {**SUMMARY, "context_hit_at_1": 0.95, "candidate_mrr": 0.9}
    assert regressions(SUMMARY, better) == []


def test_lower_score_is_a_regression():
    worse = {**SUMMARY, "context_mrr": 0.8}
    assert regressions(SUMMARY, worse) == ["context_mrr: 0.900 -> 0.800"]


def test_search_leg_returning_nothing_is_a_regression():
    worse = {**SUMMARY, "vector_zero_result_rate": 1.0}
    assert regressions(SUMMARY, worse) == ["vector_zero_result_rate: 0.000 -> 1.000"]


def test_other_session_chunks_fail_even_if_baseline_had_some():
    leaked = {**SUMMARY, "other_session_chunks": 2}
    problems = regressions({**SUMMARY, "other_session_chunks": 2}, leaked)
    assert len(problems) == 1
    assert "session filtering" in problems[0]


def test_rank_changes_lists_moved_questions_only():
    baseline = {
        "a": {"candidate_hit_rank": 1, "context_hit_rank": 1},
        "b": {"candidate_hit_rank": 2, "context_hit_rank": 1},
    }
    current = {
        "a": {"candidate_hit_rank": 1, "context_hit_rank": 1},
        "b": {"candidate_hit_rank": 4, "context_hit_rank": None},
    }
    assert rank_changes(baseline, current) == [
        "b candidate_hit_rank: 2 -> 4",
        "b context_hit_rank: 1 -> None",
    ]
