# What the AI evaluations showed, and what changed because of them

Results are in `AI_QUALITY.md` (regenerate with `uv run python -m evals.run_all` from `apps/api`; about 6 US cents).

## How the measurements were built, and why

- **Document Q&A:** real grant descriptions are the haystack; facts with random, unguessable values are planted at known
  places, so the right answer is exact. Questions about invented things test refusal; a planted "ignore all
  previous instructions" sentence tests injection. A perfect oracle, an always-refusing model, a fabricator and an
  obedient model are run through the same code in `tests/test_aieval.py`, so a bug in the harness cannot masquerade as a
  quality result.
- **Fit check:** each test profile is one unambiguous applicant type (or deliberately vague), and Grants.gov lists each
  grant's eligible types as data, so "met" can be scored exactly. The sample was stratified so that "the grant does
  NOT list your type" (where false assurance would happen) has 33 cases, not 4.
- **Review builder:** annotation coverage is objective. Faithfulness is judged by a model, strictly, one claim at a time.

## Mistakes in my own first measurements (kept here on purpose)

1. **Q&A: 18% "wrong answers with a verified citation" was wrong.** All 12 were genuine sentences from the real grant
   text that legitimately answered the question (the real program officer, the real "typical period of performance"),
   competing with my planted facts. Facts and questions now name an invented program track so nothing real competes.
   The true figure is 0 of 68.
2. **Fit: a perfect score on an easy test.** The first sample had only 4 "type not listed" cases, so false assurance could
   not be measured (confidence interval 0 to 49%). Re-sampled to 33.
3. **Review: judged against the wrong abstracts.** The evaluation searched OpenAlex a second time to recover abstracts and got a
   different set, so paper ids no longer matched. That produced alarming "unsupported" rates (15 to 23%) that were
   not real. It now reuses the exact papers the builder used, and asserts the ids line up. Production was never affected.
4. **Fit: my prompt edit deleted the instruction to put the applicant-type id in `ref`**, which threw away 59% of the
   model's answers and collapsed "met" to 25%. The unit tests did not notice because the fake model never reads the
   prompt, so there is now a test that the prompt contains that instruction.

## Real weaknesses found, and the fixes

| Weakness | Measured before | Fix | Measured after |
|---|---|---|---|
| Fit check said an applicant type was met when the grant does not list it | 7/33 (21%) | strict second check per claim ("does this statement by itself establish this requirement?"); catch-all "Others" entries can never be met | 0/33 (CI 0 to 10%) |
| Fit check accepted a vague statement ("I work at a university") as proof of a *public* institution | 8/16 (50%), mostly this | same second check, plus a sharper prompt | 0/16 (CI 0 to 19%) |
| Fit check, correct "met" for a type the grant lists | 23/24 (96%) | (cost of the above) | 23/24 (96%) |

The second check fails closed: if it errors or does not answer, a "met" or "not met" falls back to "unclear". It also
means many model claims are downgraded (44% of checks had at least one), which is the point: those were mostly claims
that did not hold up.

## Still weak or unproven

- **Theme summaries in the review builder are the weakest output:** only about two thirds are judged fully supported by the
  papers' abstracts; the rest overgeneralise. Annotations (one paper each) are much better (about 98%). Treat theme
  summaries as a draft, and consider the same narrow-check approach for them.
- **One hallucination in a first run** (an invented "Drokestal Fellowship supplement" answered with an unrelated real deadline,
  with a real quote) did not recur in 64 further unanswerable questions: about 1 in 96 overall. The citation check cannot
  catch a real quote that does not answer the question; only the model's judgement does.
- **Sample sizes are small** (68 and 64 Q&A, 57 and 16 fit, 48 annotations). Read the confidence intervals. A "0 of 33" is
  consistent with a true rate up to about 10%.
- **The review judge is the model that wrote the annotations**, and models rate their own work generously.
- **What is not measured:** answer quality on real researchers' real documents (tables, equations, two columns), scanned PDFs, other
  models, and search relevance across the full 84,000-opportunity corpus (the labelled set predates it).
- **Run-to-run variation:** temperature 0 is not fully deterministic. Small differences between runs are noise.

## Review theme summaries: what was tried (2026-11-03)

Original: summaries written in the same call as the grouping, 7/11 (64%) judged fully supported.
1. Rewrite from the verified paper notes, then a model check of each sentence against the cited abstracts: 10/13 (77%).
   The check was gpt-4o-mini, the same model as the judge, and it dropped **zero** sentences, so it added nothing.
2. Same, plus rules the model cannot argue with (one paper per sentence; a verbatim quote from that paper; every number
   and 80% of the longer words must appear in that quote), a stricter check prompt, and one repair round for themes where
   every sentence was rejected: 6/8 (75%) fully supported, but **7 of 15 themes (47%) were left without a summary**, and
   38 sentences were rejected on the way.

Conclusion: the faithfulness of the summaries that are shown did not measurably improve (75% vs 77%, samples of 8 and 13),
and the cost is a summary on only about half the themes. The strict version is what ships, because an unsupported
sentence in a research tool is worse than a missing one, and each paper still has its own verified annotation and quote.
Nothing here shows the strict rules beat the simple ones; a proper test needs more topics and a human check of the
judge's "partly supported" verdicts, several of which were about wording rather than claims.
