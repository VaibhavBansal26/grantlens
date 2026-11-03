# AI quality measurements

Measured 2026-11-02 on commit `f10939c`, model `meta-llama/Llama-3.1-8B-Instruct` (served by `meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo`), temperature 0, against a database of 83,658 opportunities. Cost of this run: 260 calls, 280,857 prompt + 59,854 completion tokens (billed by the provider, a few cents at most). The review builder's judge is `gpt-4o-mini` for both backends, so scores are comparable.

Rates show the count, the percentage and a 95% confidence interval. **With samples this small the intervals are wide: read the interval, not just the percentage.** Re-run with `uv run python -m evals.run_all` (see the top of `evals/run_all.py`).

### Document Q&A (planted facts in real grant text)

68 answerable and 64 unanswerable questions over 16 documents: 4 each of 2, 8 and 30 pages, plus 4 eight-page documents that contain a planted prompt-injection sentence.

| Measure | Result |
|---|---|
| Chunking kept the planted sentence whole in at least one chunk | 67/68 = 99% (95% CI 92 to 100%) |
| Retrieval put the whole planted sentence in front of the model | 66/68 = 97% (95% CI 90 to 99%) |
| Correct answer, with a verified citation | 66/68 = 97% (95% CI 90 to 99%) |
| Citation actually contains the planted fact | 66/68 = 97% (95% CI 90 to 99%) |
| **Wrong answer given with a verified citation** (the dangerous one) | 0/68 = 0% (95% CI 0 to 5%) |
| Unanswerable: clean refusal ("couldn't find support") | 45/64 = 70% (95% CI 58 to 80%) |
| Unanswerable: said "not specified" but attached an unrelated quote (confusing, not false) | 16/64 = 25% (95% CI 16 to 37%) |
| **Unanswerable: asserted an answer about something that does not exist** (hallucination) | 3/64 = 5% (95% CI 2 to 13%) |
| Model obeyed the planted injection (raw output was PWNED) | 0/32 = 0% (95% CI 0 to 11%) |
| ...and that obedience **reached the user** | 0/32 = 0% (95% CI 0 to 11%) |
| Calls that produced no usable answer at all (counted as failures above) | 0/132 = 0% (95% CI 0 to 3%) |

By document size (correct answer with verified citation):

| Size | Correct |
|---|---|
| small | 12/12 = 100% (95% CI 76 to 100%) |
| medium | 16/16 = 100% (95% CI 81 to 100%) |
| large | 22/24 = 92% (95% CI 74 to 98%) |
| injected | 16/16 = 100% (95% CI 81 to 100%) |

Answerable questions not answered correctly: 2. Of those, 0 had the fact in front of the model (a reading failure) and 2 never retrieved it (a search failure).

### Grant-fit eligibility (known applicant types)

57 checks with a clearly stated applicant type: 24 where the grant lists that type and 33 where it does not, over 26 different real open grants. Plus 16 checks with a deliberately vague applicant (right answer: unclear).

| Measure | Result |
|---|---|
| Type is listed: correctly said **met** | 11/24 = 46% (95% CI 28 to 65%) |
| Type is listed: said **not met** (wrong, and discouraging) | 0/24 = 0% (95% CI 0 to 14%) |
| Type is listed: left out or said unclear (cautious, not wrong) | 13/24 = 54% (95% CI 35 to 72%) |
| **Type is NOT listed but it said met for some entry** (false assurance) | 0/33 = 0% (95% CI 0 to 10%) |
| Said a *different* type was met (any check) | 0/57 = 0% (95% CI 0 to 6%) |
| **Vague applicant: said met for something anyway** (should be unclear) | 0/16 = 0% (95% CI 0 to 19%) |
| Checks that produced no usable answer at all | 2/73 = 3% (95% CI 1 to 9%) |
| Model proposed requirements the grant does not state (caught and dropped) | 58/73 = 79% (95% CI 69 to 87%) |
| A met / not met had no verifiable quote (downgraded to unclear) | 42/73 = 58% (95% CI 46 to 68%) |

Per applicant type:

| Applicant | Said met when listed | False assurance when not listed |
|---|---|---|
| public university | 0/4 = 0% (95% CI 0 to 49%) | 0/6 = 0% (95% CI 0 to 39%) |
| private university | 3/4 = 75% (95% CI 30 to 95%) | 0/8 = 0% (95% CI 0 to 32%) |
| nonprofit | 1/4 = 25% (95% CI 5 to 70%) | 0/4 = 0% (95% CI 0 to 49%) |
| small business | 0/4 = 0% (95% CI 0 to 49%) | 0/8 = 0% (95% CI 0 to 32%) |
| tribal government | 4/4 = 100% (95% CI 51 to 100%) | 0/3 = 0% (95% CI 0 to 56%) |
| state agency | 3/4 = 75% (95% CI 30 to 95%) | 0/4 = 0% (95% CI 0 to 49%) |

### Literature review builder

3 topics, 32 papers in total.

| Measure | Result |
|---|---|
| Reviews that could be built at all (no usable JSON = failed) | 2/3 = 67% (95% CI 21 to 94%) |
| Papers that ended up with a verified annotation | 32/32 = 100% (95% CI 89 to 100%) |
| Annotation judged **fully supported** by its abstract | 31/32 = 97% (95% CI 84 to 99%) |
| Annotation judged **partly** supported | 1/32 = 3% (95% CI 1 to 16%) |
| Annotation judged **unsupported** | 0/32 = 0% (95% CI 0 to 11%) |
| Theme summary judged fully supported by its papers' abstracts | 5/6 = 83% (95% CI 44 to 97%) |
| Theme summary judged unsupported or only partly | 1/6 = 17% (95% CI 3 to 56%) |

First-attempt quotes that failed the check (and were retried): 1 across all topics.

| Topic | Papers | Themes | Annotated | Seconds |
|---|---|---|---|---|
| deep learning for tumor segmentation in radiotherapy planning | 16 | 1 | 16 | 192 |
| federated learning privacy in medical imaging | 16 | 5 | 16 | 76 |
| community health worker interventions for diabetes | 0 | 0 | 0 | 182 |
