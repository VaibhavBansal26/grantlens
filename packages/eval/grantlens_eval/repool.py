"""Pool the top-k of every baseline per query; emit only candidates that have no grade yet."""
from pathlib import Path

import yaml

from .baselines import bm25_retriever, dense_retriever, hybrid_retriever, load_docs

K = 20


def main(out_dir: str = "grading2", batches: int = 6):
    docs = load_docs()
    by_id = {d["id"]: d for d in docs}
    bm25, dense = bm25_retriever(docs), dense_retriever(docs)
    systems = [bm25, dense, hybrid_retriever(bm25, dense)]
    queries = yaml.safe_load(Path("queries.yaml").read_text())["queries"]
    graded = {
        q["id"]: {c["id"] for c in cq["candidates"]}
        for q, cq in zip(
            queries, yaml.safe_load(Path("candidates.yaml").read_text())["queries"], strict=True
        )
    }
    todo = []
    for q in queries:
        pooled = dict.fromkeys(i for s in systems for i in s(q["text"], K))
        new = [i for i in pooled if i not in graded[q["id"]]]
        todo.append({
            "id": q["id"], "text": q["text"],
            "candidates": [
                {"id": i, "title": by_id[i]["title"][:110],
                 "abstract": " ".join(by_id[i]["abstract"][:500].split())}
                for i in new
            ],
        })
    Path(out_dir).mkdir(exist_ok=True)
    per = -(-len(todo) // batches)
    for b in range(batches):
        chunk = todo[b * per:(b + 1) * per]
        Path(out_dir, f"batch{b + 1}.yaml").write_text(
            yaml.safe_dump({"queries": chunk}, sort_keys=False, width=200)
        )
    print("new candidates:", sum(len(t["candidates"]) for t in todo),
          "per query:", [len(t["candidates"]) for t in todo])


if __name__ == "__main__":
    main()
