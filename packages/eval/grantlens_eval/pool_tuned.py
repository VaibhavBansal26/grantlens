"""Candidates for the re-grade: every grant in the top 50 of any of the four systems that has no label yet,
plus a calibration sample of already-labelled pairs (to measure how well the new grader agrees with the old labels).

  uv run python -m grantlens_eval.pool_tuned models/bge-small-grants-v1 results/regrade_pool.json
"""
import json
import sys
from pathlib import Path

import yaml

from .compare_tuned import build

DEPTH = 50


def main(model_dir: str, out: str):
    docs, queries, systems = build(model_dir)
    by_id = {d["id"]: d for d in docs}
    graded = {q["id"]: set() for q in queries}
    for pool in ("grading/batch?.graded.yaml", "grading2/batch?.graded.yaml"):
        for f in Path(".").glob(pool):
            for q in yaml.safe_load(f.read_text())["queries"]:
                graded.setdefault(q["id"], set()).update(map(str, q["grades"]))
    old = {q["id"]: q["relevant"] for q in queries}
    new, known = [], []
    for q in queries:
        pooled = dict.fromkeys(i for s in systems.values() for i in s(q["text"], DEPTH))
        new += [(q["id"], i) for i in pooled if i not in graded[q["id"]]]
        known += [(q["id"], i) for i in pooled if i in graded[q["id"]]]
    calib = known  # grade the old-labelled ones too, so one grader labels the whole pool
    texts = {q["id"]: q["text"] for q in queries}
    row = lambda qid, i, cal: {"query_id": qid, "query": texts[qid], "id": i, "calibration": cal,
                               "title": by_id[i]["title"][:140],
                               "abstract": " ".join(by_id[i]["abstract"][:700].split()),
                               "old_grade": int(old[qid].get(i, 0)) if cal else None}
    items = [row(q, i, False) for q, i in new] + [row(q, i, True) for q, i in calib]
    Path(out).write_text(json.dumps(items, indent=1))
    print(f"{len(new)} unlabelled candidates + {len(calib)} calibration pairs -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
