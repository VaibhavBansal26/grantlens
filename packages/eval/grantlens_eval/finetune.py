"""Fine-tune the embedding model on this corpus, using only the corpus itself (no evaluation labels).

Training pairs are (grant title -> start of its own description): a standard way to teach a retrieval model what a
domain's language means. Every grant that was ever graded for the evaluation is EXCLUDED from training, so the
labelled test never overlaps what the model learns from.

    uv run python -m grantlens_eval.finetune --pairs 20000 --out models/bge-small-grants-v1
"""
import argparse
import os
import random
import re
import time
from pathlib import Path

import yaml

BASE = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def graded_ids() -> set[str]:
    """External ids of every grant that appears in any evaluation pool (candidates and later re-pools)."""
    ids: set[str] = set()
    for f in [Path("candidates.yaml"), *sorted(Path("grading2").glob("batch?.yaml"))]:
        if f.exists():
            for q in yaml.safe_load(f.read_text())["queries"]:
                ids.update(str(c["id"]) for c in q["candidates"])
    for q in yaml.safe_load(Path("queries.yaml").read_text())["queries"]:
        ids.update(str(i) for i in q["relevant"])
    return ids


def select_pairs(rows: list[tuple[str, str, str]], exclude: set[str], n: int, seed: int = 7) -> list[tuple[str, str]]:
    """rows are (external_id, title, abstract). One pair per distinct title (the same program often recurs every
    year, and near-identical pairs in one batch would count each other as negatives)."""
    seen: set[str] = set()
    pairs = []
    for ext, title, abstract in rows:
        key = re.sub(r"\W+", " ", title.lower()).strip()
        if ext in exclude or key in seen or len(abstract) < 300 or len(title) < 8:
            continue
        seen.add(key)
        pairs.append((QUERY_PREFIX + title.strip(), " ".join(abstract.split())[:1200]))
    random.Random(seed).shuffle(pairs)
    return pairs[:n]


def load_rows() -> list[tuple[str, str, str]]:
    import psycopg

    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg", "postgresql")
    with psycopg.connect(dsn) as conn:
        return conn.execute("SELECT external_id, title, abstract FROM opportunity WHERE abstract IS NOT NULL").fetchall()


def train(pairs: list[tuple[str, str]], out: str, batch: int = 16, max_len: int = 128, lr: float = 2e-5,
          scale: float = 20.0, log=print) -> None:
    import torch
    from sentence_transformers import SentenceTransformer

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = SentenceTransformer(BASE, device=device)
    model.max_seq_length = max_len  # 8 GB of memory shared with the OS: longer sequences ran the GPU out of memory
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    steps = len(pairs) // batch
    warm = max(1, steps // 10)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min((s + 1) / warm, max(0.0, (steps - s) / max(1, steps - warm))))

    def embed(texts: list[str]):
        # `preprocess` replaced the deprecated `tokenize`; its output also holds non-tensor fields, which stay put
        feats = {k: (v.to(device) if hasattr(v, "to") else v) for k, v in model.preprocess(texts).items()}
        return torch.nn.functional.normalize(model(feats)["sentence_embedding"], dim=-1)

    t0, running = time.time(), []
    log(f"training on {device}: {len(pairs)} pairs, batch {batch}, {steps} steps")
    for step in range(steps):
        chunk = pairs[step * batch:(step + 1) * batch]
        a, p = embed([c[0] for c in chunk]), embed([c[1] for c in chunk])
        sims = a @ p.T * scale  # every other pair's description in the batch is a negative
        labels = torch.arange(len(chunk), device=device)
        loss = (torch.nn.functional.cross_entropy(sims, labels) + torch.nn.functional.cross_entropy(sims.T, labels)) / 2
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step(); sched.step(); opt.zero_grad()
        running.append(loss.item())
        if device == "mps" and step % 20 == 0:
            torch.mps.empty_cache()
        if (step + 1) % 25 == 0 or step + 1 == steps:
            done = (step + 1) / steps
            eta = (time.time() - t0) / done * (1 - done)
            log(f"step {step + 1}/{steps} loss {sum(running[-25:]) / len(running[-25:]):.3f} elapsed {time.time() - t0:.0f}s eta {eta:.0f}s")
    model.eval()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    model.save(out)
    log(f"saved to {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=int, default=20000)
    ap.add_argument("--out", default="models/bge-small-grants-v1")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=128)
    args = ap.parse_args()
    exclude = graded_ids()
    pairs = select_pairs(load_rows(), exclude, args.pairs)
    print(f"{len(exclude)} graded grants excluded from training; {len(pairs)} training pairs", flush=True)
    train(pairs, args.out, batch=args.batch, max_len=args.max_len, log=lambda m: print(m, flush=True))


if __name__ == "__main__":
    main()
