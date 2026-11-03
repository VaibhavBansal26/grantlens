"""Keyword search: Okapi BM25 over title + abstract, held as a sparse matrix.

Same formula and parameters as the `rank_bm25` library (tests check the scores match), but a query is one
sparse matrix-vector product instead of a Python loop over the corpus, and the index is a few hundred
megabytes at 80k documents instead of gigabytes.
"""
import logging
import re
import threading
import time
from collections import Counter

import numpy as np
from flask import current_app
from scipy import sparse
from sqlalchemy import func

from ..extensions import db
from ..models import Opportunity
from .text import doc_text

log = logging.getLogger("grantlens")
TOKEN = re.compile(r"[a-z0-9]+")
STOP = {"the", "a", "an", "of", "and", "or", "for", "to", "in", "on", "with", "by", "is", "are"}
K1, B, EPSILON = 1.5, 0.75, 0.25  # rank_bm25's defaults


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP]


class BM25Index:
    def __init__(self, rows: list[tuple[int, str, str | None]]):
        n = len(rows)
        self.ids = np.array([r[0] for r in rows], dtype=np.int64)
        self.vocab: dict[str, int] = {}
        indptr, indices, counts = [0], [], []
        doc_len = np.zeros(n)
        for i, (_, title, abstract) in enumerate(rows):
            tokens = tokenize(doc_text(title, abstract))
            doc_len[i] = len(tokens)
            for term, c in Counter(tokens).items():
                indices.append(self.vocab.setdefault(term, len(self.vocab)))
                counts.append(c)
            indptr.append(len(indices))
        if not self.vocab or doc_len.sum() == 0:
            self.W = sparse.csc_matrix((n, max(len(self.vocab), 1)))
            return
        tf = sparse.csr_matrix((counts, indices, indptr), shape=(n, len(self.vocab)), dtype=np.float64)
        df = np.bincount(tf.indices, minlength=len(self.vocab))
        idf = np.log(n - df + 0.5) - np.log(df + 0.5)
        idf[idf < 0] = EPSILON * idf.mean()  # words in over half the corpus: rank_bm25 floors them the same way
        avgdl = doc_len.mean()
        row_of = np.repeat(np.arange(n), np.diff(tf.indptr))
        denom = tf.data + K1 * (1 - B + B * doc_len[row_of] / avgdl)
        weights = idf[tf.indices] * tf.data * (K1 + 1) / denom
        self.W = sparse.csr_matrix((weights, tf.indices, tf.indptr), shape=tf.shape).tocsc()

    def scores(self, query: str) -> np.ndarray:
        terms = Counter(t for t in tokenize(query) if t in self.vocab)  # repeated query words count repeatedly
        if not terms:
            return np.zeros(len(self.ids))
        cols = np.fromiter((self.vocab[t] for t in terms), dtype=np.int64, count=len(terms))
        return np.asarray(self.W[:, cols] @ np.fromiter(terms.values(), dtype=np.float64, count=len(terms)))

    def search(self, query: str, k: int, allowed: set[int] | None = None) -> list[int]:
        scores = self.scores(query)
        if allowed is not None:
            keep = np.isin(self.ids, np.fromiter(allowed, dtype=np.int64, count=len(allowed)))
            scores = np.where(keep, scores, -np.inf)
        k = min(k, len(scores))
        top = np.argpartition(-scores, k - 1)[:k] if 0 < k < len(scores) else np.arange(len(scores))
        order = top[np.argsort(-scores[top], kind="stable")]
        return [int(self.ids[i]) for i in order if scores[i] > -np.inf]


# ---- keeping the index fresh -------------------------------------------------------------------

_lock = threading.Lock()
_state: dict = {"index": None, "stamp": None, "checked": 0.0, "building": False}


def _stamp() -> tuple:
    return tuple(db.session.query(func.count(Opportunity.id), func.max(Opportunity.updated_at)).one())


def _build() -> BM25Index:
    return BM25Index(db.session.query(Opportunity.id, Opportunity.title, Opportunity.abstract).all())


def _refresh(app) -> None:
    """Runs in a background thread: rebuild if the table changed, then swap the new index in."""
    try:
        with app.app_context():
            stamp = _stamp()
            if stamp != _state["stamp"]:
                fresh = _build()
                with _lock:
                    _state.update(index=fresh, stamp=stamp)
                log.info("lexical index refreshed", extra={"fields": {"documents": len(fresh.ids)}})
    except Exception:
        log.exception("lexical index refresh failed")
    finally:
        with _lock:
            _state["building"] = False


def get_index() -> BM25Index:
    """The first call builds the index (workers do this at startup, see warmup.py). After that, searches use
    the index in memory and a background thread refreshes it at most every LEXICAL_REFRESH_SECONDS, so a
    sync adding rows never makes a user wait. A refresh interval of 0 re-checks on every call (tests)."""
    interval = current_app.config.get("LEXICAL_REFRESH_SECONDS", 300)
    if _state["index"] is None or interval == 0:
        stamp = _stamp()
        with _lock:
            if _state["index"] is None or _state["stamp"] != stamp:
                _state.update(index=_build(), stamp=stamp, checked=time.monotonic())
            return _state["index"]
    with _lock:
        due = time.monotonic() - _state["checked"] >= interval and not _state["building"]
        if due:
            _state.update(building=True, checked=time.monotonic())
        index = _state["index"]
    if due:
        threading.Thread(target=_refresh, args=(current_app._get_current_object(),), daemon=True).start()
    return index
