"""Base vs fine-tuned embeddings on the labelled queries: dense and hybrid, per-query, with a paired bootstrap.

  uv run python -m grantlens_eval.compare_tuned models/bge-small-grants-v1
Labels were pooled from systems that used the BASE model, so a tuned model can surface grants nobody judged; those
count as not relevant here. The report says how many there are, because that bias works against the tuned model.
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch

from .baselines import EMB, QUERY_PREFIX, bm25_retriever, load_docs, rrf
from .corpus import text_of
from .metrics import hit_at_k, mrr, ndcg_at_k, recall_at_k
from .runner import load_queries

NAMES = ("ndcg@10", "recall@50", "mrr", "top5_hit")


def embed(model, docs, device, batch=16):
    model.max_seq_length = 512  # same as the base run, so only the weights differ
    out = []
    for i in range(0, len(docs), batch):
        out.append(model.encode([text_of(d, 1500) for d in docs[i:i + batch]], batch_size=batch,
                                normalize_embeddings=True, convert_to_numpy=True))
        if i % 1600 == 0:
            print(f"embedded {i}/{len(docs)}", flush=True)
            if device == "mps":
                torch.mps.empty_cache()
    return np.vstack(out)


def per_query(retrieve, queries):
    rows = []
    for q in queries:
        ranked, rel = retrieve(q["text"], 50), q["relevant"]
        unjudged = sum(1 for d in ranked[:10] if d not in rel)
        rows.append((ndcg_at_k(ranked, rel, 10), recall_at_k(ranked, rel, 50), mrr(ranked, rel),
                     hit_at_k(ranked, rel, 5), unjudged))
    return np.array(rows)


def build(model_dir: str):
    """(docs, labelled queries, {system name: retriever}) for base and tuned, dense and hybrid."""
    from sentence_transformers import SentenceTransformer

    docs = load_docs()
    ids = [d["id"] for d in docs]
    queries = [q for q in load_queries(Path("queries.yaml")) if q["relevant"]]
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    tuned_path = Path("data/embeddings_tuned.npy")
    tuned = SentenceTransformer(model_dir, device=device)
    tv = np.load(tuned_path) if tuned_path.exists() else embed(tuned, docs, device)
    if not tuned_path.exists():
        np.save(tuned_path, tv)
    base = SentenceTransformer("BAAI/bge-small-en-v1.5", device="cpu")

    def dense(model, vecs):
        cache = {}

        def r(q, k):
            if q not in cache:
                cache[q] = model.encode([QUERY_PREFIX + q], normalize_embeddings=True)[0]
            return [ids[i] for i in np.argsort(-(vecs @ cache[q]))[:k]]

        return r

    bm25 = bm25_retriever(docs)
    systems = {}
    for tag, model, vecs in (("base", base, np.load(EMB)), ("tuned", tuned, tv)):
        d = dense(model, vecs)
        systems[f"dense/{tag}"] = d
        systems[f"hybrid/{tag}"] = lambda q, k, d=d: rrf([bm25(q, 100), d(q, 100)])[:k]
    return docs, queries, systems


def main(model_dir: str, labels: str | None = None, out: str = "results/finetune.json"):
    """`labels`: a JSON {query id: {doc id: grade}} that REPLACES the queries.yaml labels (one grader for the whole pool)."""
    _docs, queries, systems = build(model_dir)
    if labels:
        extra = json.loads(Path(labels).read_text())
        for q in queries:
            q["relevant"] = {k: v for k, v in extra.get(q["id"], {}).items() if v > 0}  # replaces, one grader
        queries = [q for q in queries if q["relevant"]]
    rows = {n: per_query(r, queries) for n, r in systems.items()}

    rng = np.random.default_rng(0)
    report = {"queries": len(queries), "systems": {}, "paired": {}}
    print(f"{'system':<14}" + "".join(f"{n:>11}" for n in NAMES) + f"{'unjudged@10':>13}")
    for n, m in rows.items():
        report["systems"][n] = {**dict(zip(NAMES, m[:, :4].mean(0).round(4).tolist())), "unjudged_top10": float(m[:, 4].sum())}
        print(f"{n:<14}" + "".join(f"{v:>11.3f}" for v in m[:, :4].mean(0)) + f"{int(m[:, 4].sum()):>13}")
    for kind in ("dense", "hybrid"):
        diff = rows[f"{kind}/tuned"][:, 0] - rows[f"{kind}/base"][:, 0]
        boots = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(10000)]
        lo, hi = np.percentile(boots, [2.5, 97.5])
        report["paired"][kind] = {"ndcg@10_delta": round(float(diff.mean()), 4), "ci95": [round(float(lo), 4), round(float(hi), 4)],
                               "queries_better": int((diff > 1e-9).sum()), "queries_worse": int((diff < -1e-9).sum())}
        print(f"{kind}: nDCG@10 tuned-base = {diff.mean():+.3f} (95% CI {lo:+.3f} to {hi:+.3f}); "
              f"better on {(diff > 1e-9).sum()}, worse on {(diff < -1e-9).sum()} of {len(diff)}")
    Path(out).write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main(sys.argv[1], *(sys.argv[2:4]))
