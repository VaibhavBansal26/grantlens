# AI quality measurements

Measured 2026-11-03 on commit `bf72b97`, model `gpt-4o-mini` (served by `gpt-4o-mini-2024-07-18`), temperature 0, against a database of 83,658 opportunities. Cost of this run: 77 calls, 54,563 prompt + 9,724 completion tokens, about $0.014.

Rates show the count, the percentage and a 95% confidence interval. **With samples this small the intervals are wide: read the interval, not just the percentage.** Re-run with `uv run python -m evals.run_all` (see the top of `evals/run_all.py`).

### Literature review builder

3 topics, 48 papers in total.

| Measure | Result |
|---|---|
| Reviews that could be built at all (no usable JSON = failed) | 3/3 = 100% (95% CI 44 to 100%) |
| Papers that ended up with a verified annotation | 48/48 = 100% (95% CI 93 to 100%) |
| Annotation judged **fully supported** by its abstract | 46/48 = 96% (95% CI 86 to 99%) |
| Annotation judged **partly** supported | 2/48 = 4% (95% CI 1 to 14%) |
| Annotation judged **unsupported** | 0/48 = 0% (95% CI 0 to 7%) |
| Theme summary judged fully supported by its papers' abstracts | 10/13 = 77% (95% CI 50 to 92%) |
| Theme summary judged unsupported or only partly | 3/13 = 23% (95% CI 8 to 50%) |
| Themes left **without** a summary (every sentence failed the check) | 0/13 = 0% (95% CI 0 to 23%) |

Theme sentences dropped because the check found them unsupported: 0.

First-attempt quotes that failed the check (and were retried): 1 across all topics.

| Topic | Papers | Themes | Annotated | Seconds |
|---|---|---|---|---|
| deep learning for tumor segmentation in radiotherapy planning | 16 | 4 | 16 | 26 |
| federated learning privacy in medical imaging | 16 | 4 | 16 | 21 |
| community health worker interventions for diabetes | 16 | 5 | 16 | 27 |
