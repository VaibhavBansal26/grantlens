"""Run the AI quality evaluations and write docs/AI_QUALITY.md.

    cd apps/api && DATABASE_URL=postgresql+psycopg://grantlens:grantlens@localhost:5433/grantlens \\
        uv run python -m evals.run_all [--only qa fit review]

Needs the dev database up and OPENAI_API_KEY in the repo's .env. It spends real money (a few cents with gpt-4o-mini).
"""
import argparse
import json
import subprocess
import time
from datetime import date
from pathlib import Path

from grantlens_api.extensions import db
from grantlens_api.models import Opportunity
from grantlens_api.retrieval.clean import clean_text

from . import common, fit_eval, qa_eval, review_eval

ROOT = Path(__file__).resolve().parents[3]


def haystack(n: int = 250) -> list[str]:
    """Real grant descriptions, in a fixed pseudo-random order, to hide the planted facts in."""
    rows = (db.session.query(Opportunity.abstract)
            .filter(db.func.length(Opportunity.abstract).between(2500, 12000))
            .order_by(db.func.md5(db.cast(Opportunity.id, db.String) + "haystack")).limit(n).all())
    return [clean_text(a) for (a,) in rows]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=["qa", "fit", "review"], default=["qa", "fit", "review"])
    args = ap.parse_args()
    llm, app = common.make_llm(), common.make_app()
    sections, raw, timings = [], {}, {}
    with app.app_context():
        corpus = db.session.query(Opportunity).count()
        for name, run, report in (("qa", lambda: qa_eval.run(haystack(), llm), qa_eval.report),
                                  ("fit", lambda: fit_eval.run(llm), fit_eval.report),
                                  ("review", lambda: review_eval.run(llm), review_eval.report)):
            if name not in args.only:
                continue
            t0 = time.perf_counter()
            raw[name] = run()
            timings[name] = round(time.perf_counter() - t0)
            sections += report(raw[name]) + [""]
            print(f"{name}: done in {timings[name]}s", flush=True)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], check=False, cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    measured = (f"Measured {date.today().isoformat()} on commit `{commit}`, model `{llm.model}`, temperature 0, "
                f"against a database of {corpus:,} opportunities. Cost of this run: {common.cost_estimate(llm.usage, llm.model)}.")
    caution = ("Rates show the count, the percentage and a 95% confidence interval. **With samples this small the intervals "
               "are wide: read the interval, not just the percentage.** Re-run with `uv run python -m evals.run_all` "
               "(see the top of `evals/run_all.py`).")
    header = ["# AI quality measurements", "", measured, "", caution, ""]
    (ROOT / "docs" / "AI_QUALITY.md").write_text("\n".join(header + sections))
    out = ROOT / "packages" / "eval" / "results"
    out.mkdir(exist_ok=True, parents=True)
    (out / "ai_quality.json").write_text(json.dumps({"model": llm.model, "commit": commit, "usage": llm.usage,
                                                      "seconds": timings, "raw": raw}, indent=1, default=str))
    print("cost:", common.cost_estimate(llm.usage, llm.model))


if __name__ == "__main__":
    main()
