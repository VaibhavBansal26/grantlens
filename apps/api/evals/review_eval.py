"""Literature review builder: coverage (objective) and faithfulness (judged by a model, so treat it as a rough guide).

The quote check already guarantees every annotation carries words that really are in the paper's abstract.
What it cannot guarantee is that the annotation SENTENCE says nothing the abstract does not. That is what the
judge is asked, strictly, one annotation at a time. The judge is the same model that wrote the annotations, and
models tend to rate their own writing generously, so the support rate is more likely too high than too low.
"""
import time

from grantlens_api import reviews
from grantlens_api.llm import LLMError
from grantlens_api.retrieval.clean import clean_text

from .common import row

TOPICS = ["deep learning for tumor segmentation in radiotherapy planning",
          "federated learning privacy in medical imaging",
          "community health worker interventions for diabetes"]

JUDGE_SYSTEM = (
    "You are a strict fact-checker. You are given source text and a claim. Decide whether the source supports "
    "everything the claim says. 'supported': every statement in the claim is stated in, or directly implied by, the "
    "source. 'partial': some statements are supported but at least one is unsupported, exaggerated or too specific. "
    "'unsupported': the claim contradicts the source or invents its content. Judge only against the source text given."
)
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string", "enum": ["supported", "partial", "unsupported"]}, "reason": {"type": "string"}},
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}


def judge(llm, source: str, claim: str) -> dict:
    out = llm.complete_json(JUDGE_SYSTEM, f"SOURCE:\n{source}\n\nCLAIM:\n{claim}", JUDGE_SCHEMA, max_tokens=250)
    return {"verdict": out["verdict"], "reason": out["reason"], "claim": claim, "source": source[:900]}


def run(llm, topics: list[str] | None = None, papers: int = 16, judge_llm=None) -> dict:
    judge_llm = judge_llm or llm  # use one fixed judge for every backend, so scores are comparable
    results = {"reviews": [], "annotations": [], "themes": []}
    for topic in topics or TOPICS:
        # One search, reused: searching again would return a different set and order, so "P3" would no longer be
        # the paper the review called P3 (an earlier version of this evaluation did exactly that).
        found, skipped, ok = reviews.gather(topic, llm, 2021, papers)
        abstracts = {f"P{i}": p.abstract for i, p in enumerate(found, 1)}
        original = reviews.gather
        reviews.gather = lambda *a, found=found, skipped=skipped, ok=ok, **k: (found, skipped, ok)
        try:
            t0 = time.perf_counter()
            r = reviews.build(topic, llm, year_from=2021, max_papers=papers)
            elapsed = time.perf_counter() - t0
        except LLMError:
            results["reviews"].append({"topic": topic, "papers": 0, "themes": 0, "annotated": 0, "unverified_first_pass": 0,
                                       "removed_refs": 0, "seconds": round(time.perf_counter() - t0), "failed": True})
            continue
        finally:
            reviews.gather = original
        by_id = {p["id"]: p for p in r.papers}
        assert all(by_id[i]["title"] == clean_text(found[int(i[1:]) - 1].title) for i in by_id), "paper ids misaligned"
        results["reviews"].append({
            "topic": topic, "papers": len(r.papers), "themes": len(r.themes),
            "annotated": sum(1 for p in r.papers if p["annotation"]), "unverified_first_pass": r.unverified_annotations,
            "removed_refs": r.removed_citations, "seconds": round(elapsed), "failed": False,
        })
        for p in r.papers:
            if p["annotation"] and p["id"] in abstracts and by_id[p["id"]]["title"]:
                results["annotations"].append({"topic": topic, "id": p["id"], **judge(judge_llm, abstracts[p["id"]], p["annotation"])})
        for t in r.themes:
            if t["summary"] and t["title"] != reviews.OTHER:
                source = "\n\n".join(f"{pid}: {abstracts[pid][:700]}" for pid in t["papers"] if pid in abstracts)
                if source:
                    results["themes"].append({"topic": topic, **judge(judge_llm, source, t["summary"])})
    return results


def report(res: dict) -> list[str]:
    revs, ann, th = res["reviews"], res["annotations"], res["themes"]
    papers, annotated = sum(r["papers"] for r in revs), sum(r["annotated"] for r in revs)
    retried = sum(r["unverified_first_pass"] for r in revs)
    out = ["### Literature review builder", "", f"{len(revs)} topics, {papers} papers in total.", "",
           "| Measure | Result |", "|---|---|",
           row("Reviews that could be built at all (no usable JSON = failed)", sum(not r.get("failed") for r in revs), len(revs)),
           row("Papers that ended up with a verified annotation", annotated, papers),
           row("Annotation judged **fully supported** by its abstract", sum(a["verdict"] == "supported" for a in ann), len(ann)),
           row("Annotation judged **partly** supported", sum(a["verdict"] == "partial" for a in ann), len(ann)),
           row("Annotation judged **unsupported**", sum(a["verdict"] == "unsupported" for a in ann), len(ann)),
           row("Theme summary judged fully supported by its papers' abstracts", sum(t["verdict"] == "supported" for t in th), len(th)),
           row("Theme summary judged unsupported or only partly", sum(t["verdict"] != "supported" for t in th), len(th)),
           "", f"First-attempt quotes that failed the check (and were retried): {retried} across all topics.", "",
           "| Topic | Papers | Themes | Annotated | Seconds |", "|---|---|---|---|---|"]
    out += [f"| {r['topic']} | {r['papers']} | {r['themes']} | {r['annotated']} | {r['seconds']} |" for r in revs]
    return out
