import re
import threading

import numpy as np
from rank_bm25 import BM25Okapi
from sqlalchemy import func

from ..extensions import db
from ..models import Opportunity
from .text import doc_text

TOKEN = re.compile(r"[a-z0-9]+")
STOP = {"the", "a", "an", "of", "and", "or", "for", "to", "in", "on", "with", "by", "is", "are"}


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP]


class BM25Index:
    def __init__(self, rows: list[tuple[int, str, str | None]]):
        self.ids = np.array([r[0] for r in rows])
        self.bm25 = BM25Okapi([tokenize(doc_text(t, a)) for _, t, a in rows])

    def search(self, query: str, k: int, allowed: set[int] | None = None) -> list[int]:
        scores = self.bm25.get_scores(tokenize(query))
        if allowed is not None:
            scores = np.where(np.isin(self.ids, list(allowed)), scores, -np.inf)
        order = np.argsort(-scores)[:k]
        return [int(self.ids[i]) for i in order if scores[i] > -np.inf]


_lock = threading.Lock()
_cache: dict = {}


def get_index() -> BM25Index:
    """Rebuilt when the table changes (row count / latest update), shared across requests."""
    stamp = db.session.query(func.count(Opportunity.id), func.max(Opportunity.updated_at)).one()
    with _lock:
        if _cache.get("stamp") != tuple(stamp):
            rows = db.session.query(Opportunity.id, Opportunity.title, Opportunity.abstract).all()
            _cache.update(stamp=tuple(stamp), index=BM25Index(rows))
        return _cache["index"]
