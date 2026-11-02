import pytest

from grantlens_eval.metrics import hit_at_k, mrr, ndcg_at_k, recall_at_k
from grantlens_eval.runner import evaluate

REL = {"a": 2, "b": 1}


def test_perfect_ranking():
    assert ndcg_at_k(["a", "b", "x"], REL, 10) == pytest.approx(1.0)
    assert recall_at_k(["a", "b"], REL, 2) == 1.0


def test_worse_ranking_scores_lower():
    assert ndcg_at_k(["x", "b", "a"], REL, 10) < 1.0
    assert mrr(["x", "b", "a"], REL) == pytest.approx(0.5)
    assert hit_at_k(["x", "y", "a"], REL, 2) == 0.0 and hit_at_k(["x", "a"], REL, 2) == 1.0


def test_no_relevant_docs():
    assert ndcg_at_k(["a"], {}, 10) == 0.0 and recall_at_k(["a"], {}, 5) == 0.0


def test_evaluate_skips_unlabelled_and_averages():
    qs = [{"text": "t", "relevant": {"a": 1}}, {"text": "u", "relevant": {}}]
    out = evaluate(lambda q, k: ["a"], qs)
    assert out["queries"] == 1 and out["ndcg@10"] == pytest.approx(1.0)
    with pytest.raises(ValueError):
        evaluate(lambda q, k: [], [{"text": "u", "relevant": {}}])
