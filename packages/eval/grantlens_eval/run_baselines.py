import json
import sys
from pathlib import Path

from .baselines import (
    bm25_retriever,
    dense_retriever,
    embed_corpus,
    hybrid_retriever,
    load_docs,
)
from .corpus import export
from .runner import evaluate, load_queries


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "snapshot":
        print(f"exported {export()} documents")
        return
    docs = load_docs()
    if cmd == "embed":
        embed_corpus(docs)
        return
    queries = load_queries(Path("queries.yaml"))
    bm25, dense = bm25_retriever(docs), dense_retriever(docs)
    systems = {"bm25": bm25, "dense": dense, "hybrid_rrf": hybrid_retriever(bm25, dense)}
    results = {"corpus_size": len(docs), **{n: evaluate(r, queries) for n, r in systems.items()}}
    Path("results").mkdir(exist_ok=True)
    Path("results/baselines.json").write_text(json.dumps(results, indent=2))
    print(f"corpus={len(docs)} docs, labelled queries={results['bm25']['queries']}")
    print(f"{'system':<12}{'ndcg@10':>9}{'recall@50':>11}{'mrr':>7}{'top5_hit':>10}")
    for n in systems:
        m = results[n]
        print(f"{n:<12}{m['ndcg@10']:>9.3f}{m['recall@50']:>11.3f}{m['mrr']:>7.3f}{m['top5_hit']:>10.3f}")


if __name__ == "__main__":
    main()
