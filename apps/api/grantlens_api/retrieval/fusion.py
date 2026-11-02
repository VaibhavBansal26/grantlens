def rrf(rankings: dict[str, list[int]], k: int = 60) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion over named rankings; returns (id, score) best first."""
    score: dict[int, float] = {}
    for ranked in rankings.values():
        for rank, doc in enumerate(ranked, 1):
            score[doc] = score.get(doc, 0.0) + 1 / (k + rank)
    return sorted(score.items(), key=lambda kv: kv[1], reverse=True)
