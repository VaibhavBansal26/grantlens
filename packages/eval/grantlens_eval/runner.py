from collections.abc import Callable
from pathlib import Path

import yaml

from .metrics import hit_at_k, mrr, ndcg_at_k, recall_at_k

Retriever = Callable[[str, int], list[str]]  # (query, k) -> ranked opportunity ids


def load_queries(path: Path) -> list[dict]:
    queries = yaml.safe_load(path.read_text())["queries"]
    for q in queries:
        q["relevant"] = {str(k): int(v) for k, v in (q.get("relevant") or {}).items()}
    return queries


def evaluate(retrieve: Retriever, queries: list[dict], depth: int = 50) -> dict[str, float]:
    labelled = [q for q in queries if q["relevant"]]
    if not labelled:
        raise ValueError("no queries have relevance labels yet")
    rows = []
    for q in labelled:
        ranked = retrieve(q["text"], depth)
        rel = q["relevant"]
        rows.append((
            ndcg_at_k(ranked, rel, 10), recall_at_k(ranked, rel, 50),
            mrr(ranked, rel), hit_at_k(ranked, rel, 5),
        ))
    n = len(rows)
    names = ("ndcg@10", "recall@50", "mrr", "top5_hit")
    return {"queries": n, **{name: sum(r[i] for r in rows) / n for i, name in enumerate(names)}}
