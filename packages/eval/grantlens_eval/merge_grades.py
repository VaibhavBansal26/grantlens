"""Merge graded batch files into queries.yaml (`relevant` = grade>0), validating coverage."""
import sys
from collections import Counter
from pathlib import Path

import yaml


def main(base: str = "grading", candidates: str = "candidates.yaml", queries: str = "queries.yaml"):
    cands = {q["id"]: q for q in yaml.safe_load(Path(candidates).read_text())["queries"]}
    grades: dict[str, dict[str, int]] = {}
    for f in sorted(Path(base).glob("batch*.graded.yaml")):
        for q in yaml.safe_load(f.read_text())["queries"]:
            grades[q["id"]] = {str(k): int(v) for k, v in q["grades"].items()}
    problems = []
    for qid, q in cands.items():
        want = {c["id"] for c in q["candidates"]}
        got = set(grades.get(qid, {}))
        if want != got:
            problems.append(f"{qid}: missing={sorted(want - got)} extra={sorted(got - want)}")
        if any(v not in (0, 1, 2) for v in grades.get(qid, {}).values()):
            problems.append(f"{qid}: grade outside 0-2")
    if problems:
        sys.exit("\n".join(problems))
    doc = yaml.safe_load(Path(queries).read_text())
    for q in doc["queries"]:
        q["relevant"] = {k: v for k, v in grades[q["id"]].items() if v > 0}
        q["label_source"] = "llm_pregrade"
    Path(queries).write_text(yaml.safe_dump(doc, sort_keys=False, width=140))
    dist = Counter(v for g in grades.values() for v in g.values())
    print(f"merged {len(grades)} queries; grades: {dict(sorted(dist.items()))}")
    empty = [q["id"] for q in doc["queries"] if not q["relevant"]]
    print("queries with no relevant grants:", empty or "none")
    print("queries with no grade-2:", [q["id"] for q in doc["queries"] if 2 not in q["relevant"].values()] or "none")


if __name__ == "__main__":
    main()
