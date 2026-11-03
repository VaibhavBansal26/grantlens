"""Small HTTP load test: mixed read traffic against a running stack, with latency percentiles.

  uv run --project apps/api python scripts/loadtest.py --base http://localhost:3100 -c 8 -s 30

429 (rate limited) is counted apart from errors: a correctly limited client is not a failure, but
it means you measured the limiter and not the server. For capacity numbers start the API with
RATELIMIT_ENABLED=0 (never in production).
"""
import argparse
import asyncio
import random
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

QUERIES = [
    "early-career funding for AI in cancer imaging", "machine learning for medical image segmentation",
    "Alzheimer's disease biomarker discovery", "mental health services in rural communities",
    "opioid use disorder treatment", "health equity community interventions", "maternal and infant health",
    "cardiovascular disease prevention", "diabetes digital health intervention", "pandemic preparedness",
    "antimicrobial resistance therapeutics", "climate change public health", "STEM education undergraduates",
    "quantum computing algorithms", "cybersecurity critical infrastructure", "battery materials energy storage",
    "sustainable agriculture food security", "water quality environmental justice", "SBIR biotechnology",
    "veterans PTSD treatment", "rare disease gene therapy", "nursing workforce training",
    "AI ethics responsible innovation", "research infrastructure core facilities", "aging long-term care",
]


PREFIX = "/api"  # "" when talking to the Flask API directly instead of through the web app


async def one(client: httpx.AsyncClient, kind: str, ids: list[int]) -> tuple[str, int, float]:
    path = PREFIX + {
        "search": lambda: f"/search?q={random.choice(QUERIES)}&mode=hybrid&k=10",
        "detail": lambda: f"/opportunities/{random.choice(ids)}",
        "deadlines": lambda: "/deadlines?start=2026-11-01&end=2026-12-31",
    }[kind]()
    t0 = time.perf_counter()
    try:
        status = (await client.get(path)).status_code
    except httpx.HTTPError:
        status = 0
    return kind, status, (time.perf_counter() - t0) * 1000


async def worker(client, stop, mix, ids, out):
    kinds, weights = zip(*mix.items(), strict=True)
    while time.monotonic() < stop:
        out.append(await one(client, random.choices(kinds, weights)[0], ids))


def pct(values: list[float], p: float) -> float:
    return statistics.quantiles(values, n=100)[int(p) - 1] if len(values) >= 100 else max(values)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3100")
    ap.add_argument("-c", "--concurrency", type=int, default=8)
    ap.add_argument("-s", "--seconds", type=int, default=30)
    ap.add_argument("--mix", default="search=70,detail=20,deadlines=10")
    ap.add_argument("--assert-p95", type=float, default=None, metavar="MS",
                    help="exit 1 unless search p95 is under MS and there were no errors (for CI)")
    ap.add_argument("--synthetic-queries", action="store_true",
                    help="query with words from the synthetic corpus (scripts/seed_synthetic.py), not English")
    ap.add_argument("--json", default=None, help="also write the results to this file")
    ap.add_argument("--api-prefix", default="/api", help="path prefix of the API; '' to hit Flask directly")
    a = ap.parse_args()
    global PREFIX
    PREFIX = a.api_prefix
    if a.synthetic_queries:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from synthetic_vocab import vocabulary, zipf_weights

        vocab = vocabulary()
        rng = random.Random(5)
        QUERIES[:] = [" ".join(rng.choices(vocab, zipf_weights(len(vocab)), k=rng.randint(2, 6))) for _ in range(200)]
    mix = {k: int(v) for k, v in (kv.split("=") for kv in a.mix.split(","))}
    limits = httpx.Limits(max_connections=a.concurrency)
    async with httpx.AsyncClient(base_url=a.base, timeout=120, limits=limits) as client:
        warm = await client.get(f"{PREFIX}/search?q=cancer+imaging&k=20")  # also builds the keyword index
        ids = [r["id"] for r in warm.json()["results"]] or [1]
        out: list[tuple[str, int, float]] = []
        stop = time.monotonic() + a.seconds
        t0 = time.monotonic()
        await asyncio.gather(*(worker(client, stop, mix, ids, out) for _ in range(a.concurrency)))
        elapsed = time.monotonic() - t0
    print(f"{len(out)} requests in {elapsed:.0f}s = {len(out) / elapsed:.1f} req/s at concurrency {a.concurrency}")
    print("status codes:", dict(Counter(s for _, s, _ in out)), "(0 = connection error, 429 = rate limited)")
    for kind in mix:
        ok = sorted(ms for k, s, ms in out if k == kind and s == 200)
        if ok:
            print(f"{kind:10} n={len(ok):5} p50={statistics.median(ok):6.0f} ms  p95={pct(ok, 95):6.0f} ms  "
                  f"p99={pct(ok, 99):6.0f} ms  max={ok[-1]:6.0f} ms")
    bad = sum(1 for _, s, _ in out if s not in (200, 429))
    print(f"errors (not 200/429): {bad}")
    search_ok = sorted(ms for k, s, ms in out if k == "search" and s == 200)
    p95 = pct(search_ok, 95) if search_ok else float("inf")
    if a.json:
        import json

        Path(a.json).write_text(json.dumps({
            "concurrency": a.concurrency, "seconds": a.seconds, "requests": len(out), "errors": bad,
            "req_per_s": round(len(out) / elapsed, 1),
            "search_p50_ms": round(statistics.median(search_ok)) if search_ok else None,
            "search_p95_ms": round(p95) if search_ok else None,
            "rate_limited": sum(1 for _, s, _ in out if s == 429)}, indent=1))
    if a.assert_p95 is not None and (bad or p95 >= a.assert_p95):
        print(f"FAILED: search p95 {p95:.0f} ms (limit {a.assert_p95:.0f}), errors {bad}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
