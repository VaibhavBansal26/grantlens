from functools import lru_cache

MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer  # optional `ml` dependency group

    return SentenceTransformer(MODEL)


def embed_documents(texts: list[str]) -> list[list[float]]:
    vecs = _model().encode(texts, batch_size=32, normalize_embeddings=True)
    return vecs.tolist()


def embed_query(query: str) -> list[float]:
    return _model().encode([QUERY_PREFIX + query], normalize_embeddings=True)[0].tolist()
