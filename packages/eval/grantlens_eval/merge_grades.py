"""Merge graded batch files into queries.yaml (`relevant` = grade>0), validating coverage.

Each pool is (input dir, graded dir): grading/ holds pool 1, grading2/ the later re-pool.
"""
import sys
from collections import Counter
from pathlib import Path

import yaml

POOLS = ["grading", "grading2"]


def _expected(pool: str, candidates: str) -> dict[str, set[str]]:
    if pool == "grading":
        qs = yaml.safe_load(Path(candidates).read_text())["queries"]
    else:
        qs = [q for f in sorted(Path(pool).glob("batch?.yaml"))
              for q in yaml.safe_load(f.read_text())["queries"]]
    return {q["id"]: {c["id"] for c in q["candidates"]} for q in qs}


def main(candidates: str = "candidates.yaml", queries: str = "queries.yaml"):
    grades: dict[str, dict[str, int]] = {}
    problems = []
    for pool in POOLS:
        if not Path(pool).exists():
            continue
        graded: dict[str, dict[str, int]] = {}
        for f in sorted(Path(pool).glob("batch*.graded.yaml")):
            for q in yaml.safe_load(f.read_text())["queries"]:
                graded[q["id"]] = {str(k): int(v) for k, v in q["grades"].items()}
        for qid, want in _expected(pool, candidates).items():
            got = set(graded.get(qid, {}))
            if want != got:
                problems.append(f"{pool}/{qid}: missing={sorted(want - got)[:5]} extra={sorted(got - want)[:5]}")
            if any(v not in (0, 1, 2) for v in graded.get(qid, {}).values()):
                problems.append(f"{pool}/{qid}: grade outside 0-2")
            grades.setdefault(qid, {}).update(graded.get(qid, {}))
    if problems:
        sys.exit("\n".join(problems))
    doc = yaml.safe_load(Path(queries).read_text())
    for q in doc["queries"]:
        q["relevant"] = {k: v for k, v in grades[q["id"]].items() if v > 0}
        q["label_source"] = "llm_pregrade"
    Path(queries).write_text(yaml.safe_dump(doc, sort_keys=False, width=140))
    dist = Counter(v for g in grades.values() for v in g.values())
    print(f"merged {len(grades)} queries; grades: {dict(sorted(dist.items()))}")


if __name__ == "__main__":
    main()
