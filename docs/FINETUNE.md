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

**Verdict on the original labels: no demonstrated improvement.** Both intervals include zero, and recall@50 and top-5 hit got worse.

Caveats: the labels were pooled from systems using the base model, so grants the tuned model newly surfaces are unjudged and
count as not relevant (top-10 unjudged: dense 71 base vs 96 tuned; hybrid 63 vs 67). That biases against the tuned model,
mostly for dense. Re-pooling and grading those would settle it for a few cents of LLM calls. Adopting a tuned model would also
mean re-embedding all 83,658 rows.

## Re-grade to remove the pooling bias

The original labels came from base-model results, so I pooled the top 50 of all four systems (base and tuned, dense and
hybrid): 2,719 query-grant pairs, 1,610 of them never labelled. All of them were graded by one grader, gpt-4o-mini at
temperature 0 with a binary rubric ("could plausibly fund the work the query describes"), and the metrics were recomputed on
those labels alone (`pool_tuned`, `evals/regrade.py`, `compare_tuned ... results/regrade_grades.json`). 30 pairs (1%) got no
valid grade and count as not relevant.

| System | nDCG@10 | recall@50 | MRR | top-5 hit |
|---|---|---|---|---|
| dense, base | 0.800 | 0.561 | 0.939 | 1.000 |
| dense, tuned | 0.824 | 0.623 | 0.961 | 1.000 |
| hybrid, base | 0.861 | 0.605 | 0.950 | 1.000 |
| hybrid, tuned | 0.868 | 0.645 | 1.000 | 1.000 |

Paired bootstrap on nDCG@10 (tuned minus base): dense +0.024 (95% CI -0.021 to +0.070, better on 14 / worse on 11);
hybrid +0.006 (95% CI -0.023 to +0.034, better on 15 / worse on 10).

**Final verdict: no statistically detectable gain; keep the base model.** The point estimates lean slightly toward the tuned
model once unjudged grants are labelled, so the earlier drop in recall was mostly the pooling bias. But the intervals include
zero, and the gain is far too small to justify re-embedding 83,658 rows.

Caveats on the grader: it is much more lenient than the original labels. It agrees with them on 76% of 1,089 already-labelled
pairs (95% CI 73 to 78%), calls 89% of the old relevant pairs relevant, and calls 59% of previously unlabelled pairs
relevant. Absolute numbers here are therefore higher than in the first table and are not comparable to it; only the
base-vs-tuned comparison within one table is meaningful. A single LLM grader is also a weaker standard than human labels.
Cost: 287 calls, about 444k tokens, roughly $0.09.
