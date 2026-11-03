# AI quality measurements

Measured 2026-11-02 on commit `8fb00ed`, model `gpt-4o-mini`, temperature 0, against a database of 83,658 opportunities. Cost of this run: 330 calls, 293,704 prompt + 36,429 completion tokens, about $0.066.

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
| Unanswerable: clean refusal ("couldn't find support") | 64/64 = 100% (95% CI 94 to 100%) |
| Unanswerable: said "not specified" but attached an unrelated quote (confusing, not false) | 0/64 = 0% (95% CI 0 to 6%) |
| **Unanswerable: asserted an answer about something that does not exist** (hallucination) | 0/64 = 0% (95% CI 0 to 6%) |
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
| Type is listed: correctly said **met** | 23/24 = 96% (95% CI 80 to 99%) |
| Type is listed: said **not met** (wrong, and discouraging) | 0/24 = 0% (95% CI 0 to 14%) |
| Type is listed: left out or said unclear (cautious, not wrong) | 1/24 = 4% (95% CI 1 to 20%) |
| **Type is NOT listed but it said met for some entry** (false assurance) | 0/33 = 0% (95% CI 0 to 10%) |
| Said a *different* type was met (any check) | 0/57 = 0% (95% CI 0 to 6%) |
| **Vague applicant: said met for something anyway** (should be unclear) | 0/16 = 0% (95% CI 0 to 19%) |
| Checks that produced no usable answer at all | 0/73 = 0% (95% CI 0 to 5%) |
| Model proposed requirements the grant does not state (caught and dropped) | 3/73 = 4% (95% CI 1 to 11%) |
| A met / not met had no verifiable quote (downgraded to unclear) | 32/73 = 44% (95% CI 33 to 55%) |

Per applicant type:

| Applicant | Said met when listed | False assurance when not listed |
|---|---|---|
| public university | 4/4 = 100% (95% CI 51 to 100%) | 0/6 = 0% (95% CI 0 to 39%) |
| private university | 4/4 = 100% (95% CI 51 to 100%) | 0/8 = 0% (95% CI 0 to 32%) |
| nonprofit | 4/4 = 100% (95% CI 51 to 100%) | 0/4 = 0% (95% CI 0 to 49%) |
| small business | 4/4 = 100% (95% CI 51 to 100%) | 0/8 = 0% (95% CI 0 to 32%) |
| tribal government | 3/4 = 75% (95% CI 30 to 95%) | 0/3 = 0% (95% CI 0 to 56%) |
| state agency | 4/4 = 100% (95% CI 51 to 100%) | 0/4 = 0% (95% CI 0 to 49%) |

### Literature review builder

3 topics, 48 papers in total.

| Measure | Result |
|---|---|
| Reviews that could be built at all (no usable JSON = failed) | 3/3 = 100% (95% CI 44 to 100%) |
| Papers that ended up with a verified annotation | 48/48 = 100% (95% CI 93 to 100%) |
| Annotation judged **fully supported** by its abstract | 47/48 = 98% (95% CI 89 to 100%) |
| Annotation judged **partly** supported | 1/48 = 2% (95% CI 0 to 11%) |
| Annotation judged **unsupported** | 0/48 = 0% (95% CI 0 to 7%) |
| Theme summary judged fully supported by its papers' abstracts | 7/11 = 64% (95% CI 35 to 85%) |
| Theme summary judged unsupported or only partly | 4/11 = 36% (95% CI 15 to 65%) |

First-attempt quotes that failed the check (and were retried): 1 across all topics.

| Topic | Papers | Themes | Annotated | Seconds |
|---|---|---|---|---|
| deep learning for tumor segmentation in radiotherapy planning | 16 | 4 | 16 | 13 |
| federated learning privacy in medical imaging | 16 | 4 | 16 | 14 |
| community health worker interventions for diabetes | 16 | 3 | 16 | 14 |
