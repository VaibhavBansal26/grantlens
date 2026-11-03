# Embedding fine-tune: result

Fine-tuned `BAAI/bge-small-en-v1.5` on 20,000 (grant title -> description) pairs from the corpus, with in-batch negatives
(MNRL, symmetric, scale 20, batch 16, max length 128, 1 epoch, ~13 min on an M1). The 1,208 grants used for evaluation
labels were excluded from training. Batch and length were cut from the plan (32/256) because the 8 GB machine ran out of
GPU memory; smaller batches mean fewer negatives, which may have limited the gain.

Evaluated on the 30 labelled queries over the 18,460-document snapshot (`uv run python -m grantlens_eval.compare_tuned`).

| System | nDCG@10 | recall@50 | MRR | top-5 hit |
|---|---|---|---|---|
| dense, base | 0.634 | 0.748 | 0.917 | 1.000 |
| dense, tuned | 0.619 | 0.707 | 0.877 | 0.967 |
| hybrid, base | 0.687 | 0.887 | 0.928 | 1.000 |
| hybrid, tuned | 0.709 | 0.817 | 0.944 | 0.933 |

Paired bootstrap on nDCG@10 (tuned minus base): dense -0.014 (95% CI -0.071 to +0.040, better on 15 / worse on 15);
hybrid +0.022 (95% CI -0.003 to +0.046, better on 21 / worse on 7).

**Verdict: no demonstrated improvement; not adopted.** Both intervals include zero, and recall@50 and top-5 hit got worse.

Caveats: the labels were pooled from systems using the base model, so grants the tuned model newly surfaces are unjudged and
count as not relevant (top-10 unjudged: dense 71 base vs 96 tuned; hybrid 63 vs 67). That biases against the tuned model,
mostly for dense. Re-pooling and grading those would settle it for a few cents of LLM calls. Adopting a tuned model would also
mean re-embedding all 83,658 rows.
