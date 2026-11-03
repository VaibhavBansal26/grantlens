# Llama 3.1 8B compared with gpt-4o-mini

Same tests, same code, same questions, temperature 0. Full reports: `AI_QUALITY.md` (gpt-4o-mini) and `AI_QUALITY_llama.md` (Llama).
Llama ran through Hugging Face Inference Providers; the provider served `meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo`,
which is a provider-chosen variant (typically a compressed copy), not necessarily the original weights. The review builder's
faithfulness judge is `gpt-4o-mini` for both, so those scores are comparable.

| Measure | gpt-4o-mini | Llama 3.1 8B |
|---|---|---|
| **Document Q&A** | | |
| Correct answer, with a verified citation | 66/68 (97%) | 66/68 (97%) |
| Wrong answer given with a verified citation (the dangerous one) | 0/68 (0%) | 0/68 (0%) |
| Unanswerable: clean refusal | 64/64 (100%) | 45/64 (70%) |
| Unanswerable: said "not specified" but attached an unrelated quote | 0/64 (0%) | 16/64 (25%) |
| Unanswerable: **asserted** an answer about something that does not exist | 0/64 (0%) | 3/64 (5%) |
| Obeyed the planted prompt injection | 0/32 (0%) | 0/32 (0%) |
| **Grant-fit check** | | |
| Applicant type listed: correctly said met | 23/24 (96%) | 11/24 (46%) |
| Type NOT listed but said met (false assurance) | 0/33 (0%) | 0/33 (0%) |
| Vague applicant accepted as a specific type | 0/16 (0%) | 0/16 (0%) |
| Checks with no usable answer at all | 0/73 (0%) | 2/73 (3%) |
| **Literature review builder** | | |
| Reviews that could be built at all | 3/3 (100%) | 2/3 (67%) |
| Annotations fully supported by the abstract | 47/48 (98%) | 31/32 (97%) |
| Theme summaries fully supported | 7/11 (64%) | 5/6 (83%) |
| Wall time, whole evaluation | Q&A 61 s, fit 52 s, review 114 s (6 parallel workers) | Q&A 201 s, fit 962 s, review 521 s (3 parallel workers) |

## What it shows

- **Reading comprehension is a tie.** With the answer in front of it, Llama 3.1 8B found and cited the planted fact 66 of 68 times, exactly like
  gpt-4o-mini, and neither obeyed the planted prompt injection. Review annotations, which need a faithful sentence about one abstract, were
  also about equal (97% vs 98% judged fully supported).
- **Knowing when not to answer is the gap.** Asked about things that do not exist in the document, gpt-4o-mini always said it couldn't find support.
  Llama refused cleanly 70% of the time. In 25% it said "not specified" **but still attached an unrelated quote as a citation** (a confusing
  presentation, not a false claim), and in 5% (3 of 64) it **asserted an answer about something invented** (for example a maximum award for a
  program that does not exist). The citation check cannot catch that, because the quote is real.
- **It follows the multi-step structure less reliably.** One of three reviews could not be built at all and 2 of 73 fit checks produced no usable
  answer, because the output was not valid JSON even after the one retry. For the fit check it said "met" for a listed applicant type only 46% of the
  time (gpt-4o-mini: 96%), mostly by being more cautious. The deterministic checks held: it never gave false assurance (0 of 33) or accepted a vague
  applicant (0 of 16).
- **Slower on this route:** the fit check took 962 s against 52 s, and the other sections 2 to 5 times longer, even allowing for 3 workers instead of
  6, so interactive features would feel noticeably slower.

## Why this is not a fair fight, and what is uncertain

- **The prompts were written and tuned for gpt-4o-mini.** Llama got the same prompts. A prompt tuned for Llama could close part of the gap.
- **One run, small samples** (64 unanswerable questions, 24 listed-type checks, 6 theme summaries): a 5% rate has a 95% interval of roughly 2 to 13%.
- **The provider's variant** is not the reference model, and hosted latency is shared and variable.
- **No schema enforcement**: gpt-4o-mini's output is forced to match the schema by OpenAI; Llama's is requested in the prompt, validated here and
  retried once. Some of Llama's weakness is that handicap, which is also the real situation for any open model on this route.
- **A larger model (for example Llama 70B) was not tested** and would probably do better; it costs more and is also slower.

## Conclusion

Llama 3.1 8B is **not a drop-in replacement** for the generation tasks here: it matches on reading and writing a faithful sentence but is worse at
declining, at structure, and at speed. It is a reasonable *optional* backend where cost or keeping text off OpenAI matters, with those limits stated.
The default stays gpt-4o-mini.

Select it with `LLM_BACKEND=hf` (needs `HF_TOKEN`; `HF_MODEL` picks the model, default `meta-llama/Llama-3.1-8B-Instruct`). Re-run the comparison with
`uv run python -m evals.run_all --backend hf` (about 30 minutes).

## A cheap improvement this suggests for any model

When an answer's text says the information is not specified, the app should present it as "not found" and not as a cited answer. The
document Q&A currently shows whatever citation the model attached. Doing this safely needs care (an answer can decline one part and answer
another), so it is not done yet.

## What about tuning?

- **Fine-tuning Llama as the writer:** not done and not recommended yet. It cannot be trained on this 8 GB laptop, there are no labelled
  "good answers", and generating them with gpt-4o-mini to train a competing model is likely against OpenAI's terms. If done, the training
  data should come from human labels or from the open model's own outputs that pass this repository's verification checks.
- **Fine-tuning the embedding model (`bge-small`):** the sensible next step. It is small enough to train here, training pairs can be built from the
  data itself (grant title and its own description; thousands of them, no model labels needed), and the labelled search set plus ablation harness
  can say honestly whether it helped, if the 30 labelled queries are split into training and held-out ones.
- **Trying a larger Llama through the same route** is one environment variable (`HF_MODEL`) and a 30-minute run.
