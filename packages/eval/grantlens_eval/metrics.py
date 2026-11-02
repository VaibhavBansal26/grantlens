import math


def recall_at_k(ranked: list[str], relevant: dict[str, int], k: int) -> float:
    rel = {d for d, g in relevant.items() if g > 0}
    return len(rel & set(ranked[:k])) / len(rel) if rel else 0.0


def hit_at_k(ranked: list[str], relevant: dict[str, int], k: int) -> float:
    return float(any(relevant.get(d, 0) > 0 for d in ranked[:k]))


def mrr(ranked: list[str], relevant: dict[str, int]) -> float:
    for i, d in enumerate(ranked, 1):
        if relevant.get(d, 0) > 0:
            return 1 / i
    return 0.0


def ndcg_at_k(ranked: list[str], relevant: dict[str, int], k: int) -> float:
    dcg = sum((2 ** relevant.get(d, 0) - 1) / math.log2(i + 1) for i, d in enumerate(ranked[:k], 1))
    ideal = sorted(relevant.values(), reverse=True)[:k]
    idcg = sum((2**g - 1) / math.log2(i + 1) for i, g in enumerate(ideal, 1))
    return dcg / idcg if idcg else 0.0
