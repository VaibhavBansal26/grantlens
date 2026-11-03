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
import time
from collections import Counter

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


async def one(client: httpx.AsyncClient, kind: str, ids: list[int]) -> tuple[str, int, float]:
    path = {
        "search": lambda: f"/api/search?q={random.choice(QUERIES)}&mode=hybrid&k=10",
        "detail": lambda: f"/api/opportunities/{random.choice(ids)}",
        "deadlines": lambda: "/api/deadlines?start=2026-11-01&end=2026-12-31",
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
    a = ap.parse_args()
    mix = {k: int(v) for k, v in (kv.split("=") for kv in a.mix.split(","))}
    limits = httpx.Limits(max_connections=a.concurrency)
    async with httpx.AsyncClient(base_url=a.base, timeout=120, limits=limits) as client:
        warm = await client.get("/api/search?q=cancer+imaging&k=20")  # also builds the keyword index
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


if __name__ == "__main__":
    asyncio.run(main())
