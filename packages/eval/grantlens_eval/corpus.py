"""Snapshot the opportunity corpus to data/corpus.jsonl so baseline numbers are reproducible."""
import json
import os
from pathlib import Path

import psycopg

CORPUS = Path("data/corpus.jsonl")


def export() -> int:
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg", "postgresql")
    CORPUS.parent.mkdir(exist_ok=True)
    n = 0
    with psycopg.connect(dsn) as conn, CORPUS.open("w") as f:
        for ext, title, abstract in conn.execute(
            "SELECT external_id, title, coalesce(abstract, '') FROM opportunity ORDER BY id"
        ):
            f.write(json.dumps({"id": ext, "title": title, "abstract": abstract}) + "\n")
            n += 1
    return n


def load() -> list[dict]:
    return [json.loads(line) for line in CORPUS.open()]


def text_of(doc: dict, max_chars: int = 2000) -> str:
    return f"{doc['title']}. {doc['abstract']}"[:max_chars]


if __name__ == "__main__":
    print(f"exported {export()} documents to {CORPUS}")
