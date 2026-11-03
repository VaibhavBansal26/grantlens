"""Rebuild the markdown reports from the saved raw results, without calling any model.

    uv run python -m evals.rescore

Used when the scoring changes (a metric is refined) so that every backend is re-scored by the same rules.
"""
import json

from . import fit_eval, qa_eval, review_eval
from .run_all import ROOT

SECTIONS = (("qa", qa_eval.report), ("fit", fit_eval.report), ("review", review_eval.report))


def main() -> None:
    for suffix in ("", "_llama"):
        results = ROOT / "packages" / "eval" / "results" / f"ai_quality{suffix}.json"
        doc = ROOT / "docs" / f"AI_QUALITY{suffix}.md"
        if not results.exists() or not doc.exists():
            continue
        raw = json.loads(results.read_text())["raw"]
        header = doc.read_text().split("### ")[0]
        body: list[str] = []
        for name, report in SECTIONS:
            if name in raw:
                body += report(raw[name]) + [""]
        doc.write_text(header + "\n".join(body))
        print(f"rescored {doc.name}")


if __name__ == "__main__":
    main()
