import random
import threading
import time

import numpy as np
import pytest
from rank_bm25 import BM25Okapi

from grantlens_api import create_app
from grantlens_api.config import TestConfig
from grantlens_api.retrieval import lexical
from grantlens_api.retrieval.lexical import BM25Index, tokenize
from grantlens_api.retrieval.text import doc_text


def corpus(n=400, seed=7):
    """Fake documents with a Zipf-like word distribution, so some words are in over half of them
    (those get a negative IDF, the awkward case) and most are rare."""
    rng = random.Random(seed)
    words = [f"w{i}" for i in range(300)]
    weights = [1 / (i + 1) for i in range(300)]
    rows = []
    for i in range(n):
        body = " ".join(rng.choices(words, weights, k=rng.randint(0, 60)))
        rows.append((1000 + i, f"title {rng.choice(words)}", body or None))
    return rows


ROWS = corpus()
REFERENCE = BM25Okapi([tokenize(doc_text(t, a)) for _, t, a in ROWS])
INDEX = BM25Index(ROWS)


@pytest.mark.parametrize("query", [
    "w0", "w0 w0 w0", "w1 w2 w3 w4", "w250 w299", "w0 w250 unknownword", "unknownword", "", "the of and",
    "w5 W5 w5", "title w10",
])
def test_scores_equal_the_reference_library(query):
    expected = REFERENCE.get_scores(tokenize(query))
    assert np.allclose(INDEX.scores(query), expected, rtol=1e-9, atol=1e-9)


def test_top_results_have_the_same_scores_as_the_reference():
    query = "w1 w2 w3 w40"
    expected = np.sort(REFERENCE.get_scores(tokenize(query)))[::-1][:10]
    ids = INDEX.search(query, 10)
    got = np.sort(np.array([INDEX.scores(query)[list(INDEX.ids).index(i)] for i in ids]))[::-1]
    assert len(ids) == 10 and np.allclose(got, expected)


def test_allowed_filter_and_small_inputs():
    allowed = {1003, 1004, 1005}
    got = INDEX.search("w0 w1", 10, allowed)
    assert set(got) <= allowed and len(got) == 3  # filtered documents never appear
    assert INDEX.search("w0", 10_000)[:1] and len(INDEX.search("w0", 10_000)) == len(ROWS)  # k larger than the corpus
    assert INDEX.search("w0", 5, allowed=set()) == []
    assert BM25Index([]).search("anything", 5) == []
    assert BM25Index([(1, "", None)]).search("anything", 5) in ([], [1])  # a corpus of empty documents does not crash


# ---- background refresh ------------------------------------------------------------------------

class FakeIndex:
    def __init__(self, label):
        self.label, self.ids = label, [1]


@pytest.fixture
def refresh(monkeypatch):
    class Cfg(TestConfig):
        LEXICAL_REFRESH_SECONDS = 300

    app = create_app(Cfg)
    state = {"stamp": "s1", "builds": 0, "gate": threading.Event(), "fail": False}
    monkeypatch.setattr(lexical, "_stamp", lambda: state["stamp"])

    def build():
        state["builds"] += 1
        if state["builds"] > 1:
            state["gate"].wait(5)  # a rebuild that takes a while
            if state["fail"]:
                raise RuntimeError("database went away")
        return FakeIndex(f"build{state['builds']}")

    monkeypatch.setattr(lexical, "_build", build)
    monkeypatch.setitem(lexical._state, "index", None)
    monkeypatch.setitem(lexical._state, "building", False)
    return app, state


def wait_until(predicate, seconds=3):
    end = time.time() + seconds
    while time.time() < end and not predicate():
        time.sleep(0.01)
    return predicate()


def test_first_call_builds_then_calls_are_instant_until_the_interval_passes(refresh):
    app, state = refresh
    with app.app_context():
        first = lexical.get_index()
        assert first.label == "build1" and state["builds"] == 1
        state["stamp"] = "s2"  # the table changed, but it is too soon to look
        assert lexical.get_index() is first and state["builds"] == 1


def test_a_due_refresh_never_blocks_and_swaps_in_when_ready(refresh):
    app, state = refresh
    with app.app_context():
        old = lexical.get_index()
        state["stamp"] = "s2"
        lexical._state["checked"] -= 1000  # the interval has passed
        t0 = time.perf_counter()
        served = lexical.get_index()
        assert served is old and time.perf_counter() - t0 < 0.5  # answered at once from the old index
        assert wait_until(lambda: state["builds"] == 2) and lexical._state["building"] is True
        assert lexical.get_index() is old  # still serving the old one while the new one builds
        state["gate"].set()
        assert wait_until(lambda: lexical._state["index"] is not old)
        assert lexical.get_index().label == "build2" and wait_until(lambda: not lexical._state["building"])


def test_an_unchanged_table_is_not_rebuilt(refresh):
    app, state = refresh
    with app.app_context():
        old = lexical.get_index()
        lexical._state["checked"] -= 1000
        lexical.get_index()  # triggers a check; the stamp is the same, so nothing is rebuilt
        assert wait_until(lambda: not lexical._state["building"]) and state["builds"] == 1
        assert lexical.get_index() is old


def test_a_failed_refresh_keeps_the_old_index_and_allows_a_retry(refresh):
    app, state = refresh
    with app.app_context():
        old = lexical.get_index()
        state["stamp"], state["fail"] = "s2", True
        state["gate"].set()
        lexical._state["checked"] -= 1000
        lexical.get_index()
        assert wait_until(lambda: state["builds"] == 2 and not lexical._state["building"])
        assert lexical.get_index() is old  # the failure did not take search down
        state["fail"] = False
        lexical._state["checked"] -= 1000
        lexical.get_index()
        assert wait_until(lambda: lexical._state["index"] is not old)
