# AI quality measurements

Measured 2026-11-03 on commit `b37a4b9`, model `gpt-4o-mini` (served by `gpt-4o-mini-2024-07-18`), temperature 0, against a database of 83,658 opportunities. Cost of this run: 74 calls, 48,876 prompt + 12,047 completion tokens, about $0.015.

Rates show the count, the percentage and a 95% confidence interval. **With samples this small the intervals are wide: read the interval, not just the percentage.** Re-run with `uv run python -m evals.run_all` (see the top of `evals/run_all.py`).

### Literature review builder

3 topics, 48 papers in total.

| Measure | Result |
|---|---|
| Reviews that could be built at all (no usable JSON = failed) | 3/3 = 100% (95% CI 44 to 100%) |
| Papers that ended up with a verified annotation | 48/48 = 100% (95% CI 93 to 100%) |
| Annotation judged **fully supported** by its abstract | 45/48 = 94% (95% CI 83 to 98%) |
| Annotation judged **partly** supported | 3/48 = 6% (95% CI 2 to 17%) |
| Annotation judged **unsupported** | 0/48 = 0% (95% CI 0 to 7%) |
| Theme summary judged fully supported by its papers' abstracts | 6/8 = 75% (95% CI 41 to 93%) |
| Theme summary judged unsupported or only partly | 2/8 = 25% (95% CI 7 to 59%) |
| Themes left **without** a summary (every sentence failed the check) | 7/15 = 47% (95% CI 25 to 70%) |

Theme sentences dropped because the check found them unsupported: 38.

First-attempt quotes that failed the check (and were retried): 0 across all topics.

| Topic | Papers | Themes | Annotated | Seconds |
|---|---|---|---|---|
| deep learning for tumor segmentation in radiotherapy planning | 16 | 5 | 16 | 28 |
| federated learning privacy in medical imaging | 16 | 5 | 16 | 26 |
| community health worker interventions for diabetes | 16 | 5 | 16 | 29 |
