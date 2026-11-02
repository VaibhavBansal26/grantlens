# Evaluation set

1. `queries.yaml`: 30 draft researcher-style queries (edit/replace freely; add your real ones).
2. `DATABASE_URL=... uv run python -m grantlens_eval.pool` writes `candidates.yaml` (20 per query).
3. Grade each candidate: `grade: 2` ideal, `1` relevant, leave `null` = not relevant. Judge topical fit, not open/closed status.
4. Copy graded ids into `queries.yaml` as `relevant: {"<external_id>": grade}`.
5. `evaluate(retriever, load_queries(...))` returns nDCG@10, Recall@50, MRR, top-5 hit.

Bias warning: candidates come from keyword search only, so labels favour keyword matches. Add grants you
find by hand, and re-pool with the embedding retriever once Phase 3 exists.

## Ablation (Flask retrieval service, 30 queries, frozen snapshot id<=18597, LLM labels)

| config | nDCG@10 | Recall@50 | MRR | top-5 hit |
|---|---|---|---|---|
| bm25 | 0.589 | 0.730 | 0.969 | 0.967 |
| dense (bge-small, pgvector HNSW) | 0.600 | 0.735 | 0.842 | 1.000 |
| hybrid (RRF) | 0.674 | 0.875 | 0.925 | 1.000 |
| hybrid + rerank (MiniLM cross-encoder) | 0.658 | 0.826 | 0.945 | 0.967 |
| hybrid + rerank (bge-reranker-base) | 0.564 | 0.740 | 0.823 | 0.933 |

Reproduce (from apps/api): `PYTHONPATH=../../packages/eval DATABASE_URL=... uv run python -m grantlens_eval.ablation 18597`.
Caveats: LLM-only labels; 30 queries (differences under ~0.03 are noise); unjudged results count as
not relevant, which penalises any system that finds grants the pools never contained.

Rerank note: both rerankers score at or below plain hybrid. Rerankers promote documents from fused ranks 20-100,
which the labelling pools (top-20 of each system) never covered, so they are counted as not relevant. The
rerank result is therefore unproven rather than proven negative; default stays hybrid without rerank.
