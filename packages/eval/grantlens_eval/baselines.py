import re
from collections.abc import Callable
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from .corpus import load, text_of

TOKEN = re.compile(r"[a-z0-9]+")
STOP = {"the", "a", "an", "of", "and", "or", "for", "to", "in", "on", "with", "by", "is", "are"}
MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
EMB = Path("data/embeddings.npy")


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP]


def bm25_retriever(docs: list[dict]) -> Callable[[str, int], list[str]]:
    index = BM25Okapi([tokenize(text_of(d)) for d in docs])
    ids = [d["id"] for d in docs]

    def retrieve(query: str, k: int) -> list[str]:
        scores = index.get_scores(tokenize(query))
        return [ids[i] for i in np.argsort(-scores)[:k]]

    return retrieve


def embed_corpus(docs: list[dict]) -> np.ndarray:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL)
    vecs = model.encode(
        [text_of(d, 1500) for d in docs], batch_size=32, normalize_embeddings=True,
        show_progress_bar=True,
    )
    np.save(EMB, vecs)
    return vecs


def dense_retriever(docs: list[dict]) -> Callable[[str, int], list[str]]:
    from sentence_transformers import SentenceTransformer

    vecs = np.load(EMB)
    assert len(vecs) == len(docs), "embeddings are stale: re-run embed"
    model = SentenceTransformer(MODEL)
    ids = [d["id"] for d in docs]

    def retrieve(query: str, k: int) -> list[str]:
        q = model.encode([QUERY_PREFIX + query], normalize_embeddings=True)[0]
        return [ids[i] for i in np.argsort(-(vecs @ q))[:k]]

    return retrieve


def rrf(rankings: list[list[str]], k: int = 60) -> list[str]:
    score: dict[str, float] = {}
    for ranked in rankings:
        for r, d in enumerate(ranked, 1):
            score[d] = score.get(d, 0.0) + 1 / (k + r)
    return sorted(score, key=score.get, reverse=True)


def hybrid_retriever(bm25, dense) -> Callable[[str, int], list[str]]:
    return lambda q, k: rrf([bm25(q, 100), dense(q, 100)])[:k]


def load_docs() -> list[dict]:
    return load()
