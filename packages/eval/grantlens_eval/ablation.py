"""Run the 30 labelled queries through the Flask retrieval service, one row per configuration.

Run from apps/api so the app and its models are importable:
  PYTHONPATH=../../packages/eval DATABASE_URL=... uv run python -m grantlens_eval.ablation 18597
The argument is the max internal opportunity id of the corpus snapshot the labels were pooled from.
"""
import json
import sys
from pathlib import Path

from .runner import evaluate, load_queries

CONFIGS = {
    "bm25": {"mode": "bm25"},
    "dense": {"mode": "dense"},
    "hybrid": {"mode": "hybrid"},
    "hybrid+rerank": {"mode": "hybrid", "rerank": True},
}


def main(max_id: int, queries_path: str = "../../packages/eval/queries.yaml",
         out: str = "../../packages/eval/results/ablation.json"):
    from grantlens_api import create_app
    from grantlens_api.retrieval.filters import Filters
    from grantlens_api.retrieval.service import search

    queries = load_queries(Path(queries_path))
    results = {"max_id": max_id}
    with create_app().app_context():
        for name, cfg in CONFIGS.items():
            def retrieve(q, k, cfg=cfg):
                return [h.external_id for h in search(q, k=k, filters=Filters(max_id=max_id), **cfg)]
            results[name] = evaluate(retrieve, queries)
            print(f"done {name}", flush=True)
    Path(out).write_text(json.dumps(results, indent=2))
    print(f"\n{'config':<16}{'ndcg@10':>9}{'recall@50':>11}{'mrr':>7}{'top5_hit':>10}")
    for name in CONFIGS:
        m = results[name]
        print(f"{name:<16}{m['ndcg@10']:>9.3f}{m['recall@50']:>11.3f}{m['mrr']:>7.3f}{m['top5_hit']:>10.3f}")


if __name__ == "__main__":
    main(int(sys.argv[1]))
