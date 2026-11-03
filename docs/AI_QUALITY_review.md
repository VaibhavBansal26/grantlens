# AI quality measurements

Measured 2026-11-03 on commit `e0e6020`, model `gpt-4o-mini` (served by `gpt-4o-mini-2024-07-18`), temperature 0, against a database of 83,658 opportunities. Cost of this run: 3 calls, 307 prompt + 177 completion tokens, about $0.000.

Rates show the count, the percentage and a 95% confidence interval. **With samples this small the intervals are wide: read the interval, not just the percentage.** Re-run with `uv run python -m evals.run_all` (see the top of `evals/run_all.py`).

### Literature review builder

3 topics, 0 papers in total.

| Measure | Result |
|---|---|
| Reviews that could be built at all (no usable JSON = failed) | 3/3 = 100% (95% CI 44 to 100%) |
| Papers that ended up with a verified annotation | n/a (0 cases) |
| Annotation judged **fully supported** by its abstract | n/a (0 cases) |
| Annotation judged **partly** supported | n/a (0 cases) |
| Annotation judged **unsupported** | n/a (0 cases) |
| Theme summary judged fully supported by its papers' abstracts | n/a (0 cases) |
| Theme summary judged unsupported or only partly | n/a (0 cases) |
| Themes left **without** a summary (every sentence failed the check) | n/a (0 cases) |

Theme sentences dropped because the check found them unsupported: 0.

First-attempt quotes that failed the check (and were retried): 0 across all topics.

| Topic | Papers | Themes | Annotated | Seconds |
|---|---|---|---|---|
| deep learning for tumor segmentation in radiotherapy planning | 0 | 0 | 0 | 0 |
| federated learning privacy in medical imaging | 0 | 0 | 0 | 0 |
| community health worker interventions for diabetes | 0 | 0 | 0 | 0 |
