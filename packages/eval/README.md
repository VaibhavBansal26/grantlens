# Evaluation set

1. `queries.yaml`: 30 draft researcher-style queries (edit/replace freely; add your real ones).
2. `DATABASE_URL=... uv run python -m grantlens_eval.pool` writes `candidates.yaml` (20 per query).
3. Grade each candidate: `grade: 2` ideal, `1` relevant, leave `null` = not relevant. Judge topical fit, not open/closed status.
4. Copy graded ids into `queries.yaml` as `relevant: {"<external_id>": grade}`.
5. `evaluate(retriever, load_queries(...))` returns nDCG@10, Recall@50, MRR, top-5 hit.

Bias warning: candidates come from keyword search only, so labels favour keyword matches. Add grants you
find by hand, and re-pool with the embedding retriever once Phase 3 exists.
