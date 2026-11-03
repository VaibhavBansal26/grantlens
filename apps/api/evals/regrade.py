"""Grade the pooled candidates from packages/eval (pool_tuned) as relevant (1) or not (0) to their query.

  uv run python -m evals.regrade ../../packages/eval/results/regrade_pool.json ../../packages/eval/results/regrade_grades.json
Uses gpt-4o-mini at temperature 0, 10 grants per call. Calibration pairs (already labelled by the original graders) are
included so agreement with the old labels can be reported. Sends public grant titles and abstracts to OpenAI.
"""
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from grantlens_api.llm import LLMError, OpenAILLM

from .common import load_openai_key, rate

SYSTEM = (
    "You judge search results for a grant-search engine. Given a researcher's search query and a list of grant "
    "opportunities (title and abstract excerpt), grade each: 1 if the grant could plausibly fund the work or need the query "
    "describes (the topic and purpose match; the grant need not be an exact fit), 0 if it is off-topic, only loosely "
    "related by a shared keyword, or aimed at a different purpose. Judge only from the text given. Grade every grant."
)
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["grades"], "properties": {"grades": {
    "type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["id", "grade"],
                               "properties": {"id": {"type": "string"}, "grade": {"type": "integer", "enum": [0, 1]}}}}}}


def grade_chunk(llm, query, chunk):
    body = "\n\n".join(f"id: {c['id']}\ntitle: {c['title']}\nabstract: {c['abstract']}" for c in chunk)
    for _ in range(2):
        try:
            got = {str(g["id"]): g["grade"] for g in llm.complete_json(SYSTEM, f"Query: {query}\n\n{body}", SCHEMA, 800)["grades"]}
        except LLMError:
            continue
        if all(c["id"] in got for c in chunk):
            return {c["id"]: got[c["id"]] for c in chunk}
    return {}  # counted as failed, never guessed


def main(pool: str, out: str):
    load_openai_key()
    llm = OpenAILLM(temperature=0)
    items = json.loads(Path(pool).read_text())
    groups = defaultdict(list)
    for it in items:
        groups[it["query_id"]].append(it)
    jobs = [(qid, g[i:i + 10]) for qid, g in groups.items() for i in range(0, len(g), 10)]
    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(lambda j: grade_chunk(llm, j[1][0]["query"], j[1]), jobs))
    grades = defaultdict(dict)
    for (qid, _), res in zip(jobs, results, strict=True):
        grades[qid].update(res)
    failed = sum(1 for it in items if it["id"] not in grades[it["query_id"]])
    cal = [it for it in items if it["calibration"] and it["id"] in grades[it["query_id"]]]
    agree = sum(1 for it in cal if (it["old_grade"] > 0) == (grades[it["query_id"]][it["id"]] > 0))
    pos_old = [it for it in cal if it["old_grade"] > 0]
    pos_new = sum(1 for it in pos_old if grades[it["query_id"]][it["id"]] > 0)
    new = [it for it in items if not it["calibration"] and it["id"] in grades[it["query_id"]]]
    Path(out).write_text(json.dumps(grades))
    print(f"graded {len(new)} new candidates, {sum(g for q in grades.values() for g in q.values())} total relevant incl. calibration; failed: {failed}")
    print("agreement with old labels on calibration pairs:", rate(agree, len(cal)))
    print("old-relevant pairs the new grader also calls relevant:", rate(pos_new, len(pos_old)))
    print("new relevant among unlabelled:", rate(sum(grades[it['query_id']][it['id']] for it in new), len(new)))
    print(f"calls {llm.usage['calls']}, tokens {llm.usage['prompt_tokens']}+{llm.usage['completion_tokens']}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
