import os
from functools import lru_cache

MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _model():
    import torch
    from sentence_transformers import SentenceTransformer  # optional `ml` dependency group

    # One short query costs the same on 1 thread as on 4 (measured: 16 ms), but several workers each running 4 compute
    # threads on the same cores fight each other and slow every request. Batches (document embedding) can opt back in.
    torch.set_num_threads(int(os.environ.get("TORCH_THREADS", "1")))
    return SentenceTransformer(MODEL)


def embed_documents(texts: list[str]) -> list[list[float]]:
    vecs = _model().encode(texts, batch_size=32, normalize_embeddings=True)
    return vecs.tolist()


@lru_cache(maxsize=2048)
def _embed_query(query: str) -> tuple[float, ...]:
    return tuple(_model().encode([QUERY_PREFIX + query], normalize_embeddings=True)[0].tolist())


def embed_query(query: str) -> list[float]:
    """Popular searches repeat, so recent query vectors are kept (about 8 KB each)."""
    return list(_embed_query(query))
