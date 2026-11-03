"""Grant-fit check: does it say "met" for the applicant type the researcher really is, and never for the others?

Ground truth is exact: Grants.gov lists each opportunity's eligible applicant types as data, and each test
profile is one clear applicant type. Literature search is switched off here, because this measures the
eligibility judgement only.
"""
from concurrent.futures import ThreadPoolExecutor

from grantlens_api import fit
from grantlens_api.extensions import db
from grantlens_api.models import Opportunity

from .common import rate, row

TAIL = " My group studies coastal ecosystem monitoring and we are preparing our first application to this agency."
PROFILES = {
    "public university": ("I am an assistant professor at a public university." + TAIL,
                          "Public and State controlled institutions of higher education"),
    "private university": ("I am a research scientist at a private university." + TAIL,
                           "Private institutions of higher education"),
    "nonprofit": ("I direct a 501(c)(3) nonprofit research institute that is not part of any university." + TAIL,
                  "Nonprofits having a 501(c)(3) status with the IRS, other than institutions of higher education"),
    "small business": ("I am the founder of a small business with twelve employees." + TAIL,
                       "Small businesses"),
    "tribal government": ("I work in the natural resources department of a federally recognized tribal government." + TAIL,
                          "Native American tribal governments (Federally recognized)"),
    "state agency": ("I am a program manager at a state government environmental agency." + TAIL,
                     "State governments"),
}


AMBIGUOUS = {  # the text does not say enough to pick an applicant type: the right answer is "unclear"
    "says only 'a university'": "I work at a university." + TAIL,
    "independent researcher": "I am an independent researcher with no institutional affiliation." + TAIL,
}


def pick_grants(listed_per_type: int = 4, unlisted_per_type: int = 8, seed: str = "fit-eval-2") -> dict[str, list[Opportunity]]:
    """For each applicant type: some real open grants that list it and, importantly, some that do not,
    so false assurance ("you qualify" when the grant does not list you) is measured on enough cases."""
    rows = (db.session.query(Opportunity)
            .filter(Opportunity.status.in_(["posted", "forecasted"]), db.func.length(Opportunity.abstract) > 1500)
            .order_by(db.func.md5(db.cast(Opportunity.id, db.String) + seed)).limit(900).all())
    pool = [o for o in rows if len(o.eligibility or []) >= 6]
    db.session.expunge_all()  # detach: workers only read attributes that are already loaded
    out = {}
    for name, (_, expected) in PROFILES.items():
        yes = [o for o in pool if expected in o.eligibility][:listed_per_type]
        no = [o for o in pool if expected not in o.eligibility][:unlisted_per_type]
        out[name] = yes + no
    out["_ambiguous"] = pool[:8]
    return out


def run_one(o: Opportunity, name: str, text: str, expected: str | None, llm) -> dict:
    present = expected in (o.eligibility or []) if expected else False
    out = fit.assess(o, text, llm)
    by = {e["requirement"]: e for e in out.eligibility}
    mine = by.get(expected) if expected else None
    # An "Unrestricted" entry (open to any type of entity) is truly met for every applicant, so it is never a mistake.
    met = [e["requirement"] for e in out.eligibility if e["status"] == "met" and not e["requirement"].startswith("Unrestricted")]
    others_met = [m for m in met if m != expected]
    return {
        "profile": name, "grant": o.id, "ambiguous": expected is None, "listed": present,
        "says_met": bool(mine and mine["status"] == "met"),
        "says_not_met": bool(mine and mine["status"] == "not_met"),
        "omitted_or_unclear": not mine or mine["status"] == "unclear",
        "any_met": bool(met),
        "wrong_met": len(others_met), "dropped": out.dropped_requirements, "downgraded": out.downgraded,
        "aims": len(out.aims), "met_entries": met,
    }


def run(llm, workers: int = 6) -> list[dict]:
    fit.literature_queries = lambda o, t, l: []  # no literature: this evaluation is about eligibility
    picked = pick_grants()
    jobs = [(o, name, PROFILES[name][0], PROFILES[name][1]) for name, grants in picked.items() if name in PROFILES for o in grants]
    jobs += [(o, name, text, None) for name, text in AMBIGUOUS.items() for o in picked["_ambiguous"]]
    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(lambda j: run_one(j[0], j[1], j[2], j[3], llm), jobs))


def report(rows: list[dict]) -> list[str]:
    typed = [r for r in rows if not r["ambiguous"]]
    amb = [r for r in rows if r["ambiguous"]]
    listed = [r for r in typed if r["listed"]]
    unlisted = [r for r in typed if not r["listed"]]
    intro = (f"{len(typed)} checks with a clearly stated applicant type: {len(listed)} where the grant lists that type and "
             f"{len(unlisted)} where it does not, over {len({r['grant'] for r in typed})} different real open grants. "
             f"Plus {len(amb)} checks with a deliberately vague applicant (right answer: unclear).")
    out = ["### Grant-fit eligibility (known applicant types)", "", intro, "", "| Measure | Result |", "|---|---|",
           row("Type is listed: correctly said **met**", sum(r["says_met"] for r in listed), len(listed)),
           row("Type is listed: said **not met** (wrong, and discouraging)", sum(r["says_not_met"] for r in listed), len(listed)),
           row("Type is listed: left out or said unclear (cautious, not wrong)", sum(r["omitted_or_unclear"] for r in listed), len(listed)),
           row("**Type is NOT listed but it said met for some entry** (false assurance)", sum(r["any_met"] for r in unlisted), len(unlisted)),
           row("Said a *different* type was met (any check)", sum(r["wrong_met"] > 0 for r in typed), len(typed)),
           row("**Vague applicant: said met for something anyway** (should be unclear)", sum(r["any_met"] for r in amb), len(amb)),
           row("Model proposed requirements the grant does not state (caught and dropped)", sum(r["dropped"] > 0 for r in rows), len(rows)),
           row("A met / not met had no verifiable quote (downgraded to unclear)", sum(r["downgraded"] > 0 for r in rows), len(rows)),
           "", "Per applicant type:", "", "| Applicant | Said met when listed | False assurance when not listed |", "|---|---|---|"]
    for name in PROFILES:
        yes = [r for r in listed if r["profile"] == name]
        no = [r for r in unlisted if r["profile"] == name]
        out.append(f"| {name} | {rate(sum(r['says_met'] for r in yes), len(yes))} | {rate(sum(r['any_met'] for r in no), len(no))} |")
    return out
