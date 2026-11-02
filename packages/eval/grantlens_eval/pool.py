"""Pull candidate opportunities per query (Postgres full-text) into a review file.

Pooling from one lexical method biases labels toward lexical matches, so also add relevant
grants you find by hand, and re-pool later with the embedding retriever (Phase 3).
"""
import os
import sys
from pathlib import Path

import psycopg
import yaml

STOP = {"with", "from", "that", "this", "research", "grants", "funding", "for"}
SQL = """
SELECT external_id, title, agency, status, close_date, left(coalesce(abstract, ''), 500),
       ts_rank(to_tsvector('english', title || ' ' || coalesce(abstract, '')), q, 33) AS score
FROM opportunity, websearch_to_tsquery('english', %s) q
WHERE to_tsvector('english', title || ' ' || coalesce(abstract, '')) @@ q
ORDER BY score DESC LIMIT %s
"""


def main(queries_path: str = "queries.yaml", out_path: str = "candidates.yaml", k: int = 20):
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg", "postgresql")
    queries = yaml.safe_load(Path(queries_path).read_text())["queries"]
    out = []
    with psycopg.connect(dsn) as conn:
        for q in queries:
            words = [w for w in q["text"].replace("'", " ").replace("-", " ").split()
                     if len(w) > 3 and w.lower() not in STOP]
            terms = " or ".join(words)
            rows = conn.execute(SQL, (terms, k)).fetchall()
            out.append({
                "id": q["id"], "text": q["text"],
                "candidates": [
                    {"id": r[0], "grade": None, "title": r[1][:110], "agency": r[2],
                     "status": r[3], "closes": str(r[4]) if r[4] else None,
                     "abstract": " ".join(r[5].split())}
                    for r in rows
                ],
            })
    Path(out_path).write_text(yaml.safe_dump({"queries": out}, sort_keys=False, width=140))
    print(f"wrote {out_path}: {sum(len(o['candidates']) for o in out)} candidates")


if __name__ == "__main__":
    main(*sys.argv[1:2])
