from functools import lru_cache

MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import CrossEncoder  # optional `ml` dependency group

    return CrossEncoder(MODEL)


def rerank(query: str, docs: list[tuple[int, str]]) -> list[tuple[int, float]]:
    """Score (id, text) pairs with a cross-encoder; returns (id, score) best first."""
    scores = _model().predict([(query, text) for _, text in docs])
    return sorted(
        ((doc_id, float(s)) for (doc_id, _), s in zip(docs, scores, strict=True)),
        key=lambda x: x[1], reverse=True,
    )
