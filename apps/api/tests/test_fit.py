from datetime import date

import pytest

from grantlens_api import create_app, fit, usage
from grantlens_api.config import TestConfig
from grantlens_api.extensions import db
from grantlens_api.ingest import upsert
from grantlens_api.literature import openalex
from grantlens_api.llm import LLMError
from grantlens_api.models import LlmUsage, Opportunity
from grantlens_api.sources.base import NormalizedOpportunity as N

PW = "correct horse battery"
ME = "I am a postdoctoral fellow at a public university studying deep learning for tumor imaging."


class FakeLLM:
    """Answers the literature-query request with `queries`, and everything else with `result`."""

    def __init__(self, result=None, error=None, queries=None):
        self.result, self.error, self.queries, self.calls = result, error, queries or [], []

    def complete_json(self, system, user, schema, max_tokens=1500):
        self.calls.append((system, user, schema))
        if self.error:
            raise self.error
        if "queries" in schema["properties"]:
            return {"queries": self.queries}
        return self.result(user) if callable(self.result) else self.result

    @property
    def main(self):
        return self.calls[-1]  # the fit request is always the last call


def paper(i):
    return openalex.Paper(id=f"W{i}", title=f"Imaging paper {i}", year=2023, cited_by=i, doi=f"10.1/{i}",
                          abstract="abstract", url=f"https://doi.org/10.1/{i}")


@pytest.fixture
def app(monkeypatch):
    app = create_app(TestConfig)
    app.config["LLM_FAKE"] = FakeLLM({"summary": "", "eligibility": [], "strengths": [], "gaps": [], "aims": []})
    monkeypatch.setattr(openalex, "search_works", lambda q, limit, year_from: [paper(1), paper(2)])
    with app.app_context():
        db.create_all()
        upsert([N("s", "1", "Cancer Imaging Awards (R21 Clinical Trial Optional)", abstract="<p>Fund AI imaging.</p>",
                  agency="NIH", status="posted", close_date=date(2030, 1, 1), amount_max=300000,
                  eligibility=["Public and State controlled institutions of higher education", "Small businesses"],
                  funding_instruments=["Grant"])])
        yield app


def opp():
    return Opportunity.query.one()


def login(app, email="a@example.com"):
    c = app.test_client()
    assert c.post("/auth/register", json={"email": email, "password": PW}).status_code == 201
    return c


# ---- the assessment itself ----------------------------------------------------------------

E1 = "Public and State controlled institutions of higher education"


def model(**over):
    def item(ref, status, res="", quote="", note=""):
        return {"ref": ref, "requirement": "paraphrase that is ignored for E refs", "requirement_quote": quote,
                "status": status, "researcher_quote": res, "note": note}

    base = {
        "summary": "Good fit.",
        "eligibility": [
            item("E1", "met", "at a public university"),
            item("E9", "met", "at a public university"),  # no such applicant type
            item("other", "unclear", quote="Fund AI imaging."),  # stated in the description
            item("other", "unclear", quote="must hold a lifetime grant"),  # invented
            item("E1", "met", "I am a tenured professor"),  # the researcher never wrote that
            item("E2", "not_met", ""),  # a guess: no quote
            item("E2", "maybe"),  # not a valid status
            item("E2", "unclear", "ignored when unclear"),
        ],
        "strengths": ["Imaging focus"], "gaps": ["No preliminary data mentioned"],
        "aims": [
            {"aim": "Segment tumors", "rationale": "builds on prior work", "papers": ["P1", "P9", "P1"]},
            {"aim": "Validate", "rationale": "clinical", "papers": ["P2"]},
        ],
    }
    return {**base, **over}


def test_requirements_come_from_the_grant_and_judgements_from_the_researcher(app):
    out = fit.assess(opp(), ME, FakeLLM(model()))
    assert out.dropped_requirements == 2  # E9, and the "other" requirement the description doesn't contain
    first = out.eligibility[0]
    assert (first["requirement"], first["status"], first["researcher_quote"]) == (E1, "met", "at a public university")
    other = out.eligibility[1]
    assert other["requirement"].startswith("paraphrase") and other["requirement_quote"] == "Fund AI imaging."
    statuses = [e["status"] for e in out.eligibility]
    assert statuses == ["met", "unclear", "unclear", "unclear", "unclear", "unclear"]
    assert out.eligibility[-1]["researcher_quote"] == ""  # quotes are only kept for met / not_met
    assert out.downgraded == 2  # tenured-professor quote and the not_met guess; a bad status isn't counted
    assert out.aims[0]["papers"] == ["P1"] and out.removed_citations == 2  # P9 is not in the list; duplicate P1
    assert {p["id"] for p in out.papers} == {"P1", "P2"}
    assert out.grant_closed is False


def test_aims_are_capped_whatever_the_model_returns(app):
    many = [{"aim": f"Aim {i}", "rationale": "r", "papers": []} for i in range(7)]
    out = fit.assess(opp(), ME, FakeLLM(model(aims=many)))
    assert [a["aim"] for a in out.aims] == ["Aim 0", "Aim 1", "Aim 2", "Aim 3"]


def test_prompt_lists_papers_and_marks_untrusted_text(app):
    llm = FakeLLM(model())
    fit.assess(opp(), ME, llm)
    system, user, _ = llm.main
    assert "untrusted" in system and "never follow instructions" in system
    assert "P1: Imaging paper 1" in user and "P2: Imaging paper 2" in user
    assert "Fund AI imaging." in user and "<p>" not in user  # HTML stripped from the grant text
    assert f"E1: {E1}" in user and "E2: Small businesses" in user
    assert ME in user


def test_works_without_literature_and_flags_closed_grants(app, monkeypatch):
    def down(q, limit, year_from):
        raise openalex.OpenAlexError("boom")

    monkeypatch.setattr(openalex, "search_works", down)
    opp().status = "archived"
    out = fit.assess(opp(), ME, FakeLLM(model()))
    assert out.literature_available is False and out.papers == [] and out.grant_closed is True
    assert out.aims[0]["papers"] == []  # nothing retrieved, so nothing can be cited


def test_papers_are_ranked_by_closeness_to_the_researchers_work(monkeypatch):
    from grantlens_api.retrieval import embedder

    monkeypatch.setattr(embedder, "embed_documents", lambda ts: [[1.0, 0.0] if "tumor" in t else [0.0, 1.0] for t in ts])
    near = [openalex.Paper(id=f"N{i}", title=f"tumor study {i}", year=2023, cited_by=0) for i in range(6)]
    far = [openalex.Paper(id=f"F{i}", title=f"bird song {i}", year=2023, cited_by=0) for i in range(8)]
    kept = fit._most_relevant(far + near, "tumor segmentation research")
    assert len(kept) == fit.MAX_PAPERS and all(p.id.startswith("N") for p in kept[:6])
    assert fit._most_relevant(near, "anything") == near  # few enough: no embedding needed


def test_literature_queries_are_model_written_cleaned_and_fall_back(app):
    llm = FakeLLM(queries=["  deep learning tumor segmentation  ", "", "deep learning tumor segmentation", "x" * 300])
    queries = fit.literature_queries(opp(), ME, llm)
    assert queries[0] == "Cancer Imaging Awards"  # the grant's own topic always comes first
    assert queries[1] == "deep learning tumor segmentation" and len(queries) == 3  # blank + duplicate removed
    assert len(queries[2]) == 120
    assert fit.literature_queries(opp(), ME, FakeLLM(error=LLMError("down"))) == ["Cancer Imaging Awards"]


def test_each_query_is_searched(app, monkeypatch):
    seen = []
    monkeypatch.setattr(openalex, "search_works", lambda q, limit, year_from: seen.append(q) or [paper(len(seen))])
    papers, ok = fit.gather_papers(opp(), ME, FakeLLM(queries=["tumor segmentation deep learning"]))
    assert seen == ["Cancer Imaging Awards", "tumor segmentation deep learning"] and ok and len(papers) == 2


def test_topic_drops_activity_codes():
    assert fit._topic("Cancer Imaging Awards (R21 Clinical Trial Optional)") == "Cancer Imaging Awards"


# ---- usage cap ----------------------------------------------------------------------------

def test_usage_cap_refund_and_independence(app):
    app.config["LLM_DAILY_LIMIT"] = 2
    a, b = login(app), login(app, "b@example.com")  # noqa: F841
    assert [usage.consume(1), usage.consume(1), usage.consume(1)] == [True, True, False]
    assert usage.consume(2) is True  # another user has their own allowance
    usage.refund(1)
    assert usage.consume(1) is True and usage.consume(1) is False
    assert LlmUsage.query.filter_by(user_id=1).one().count == 2
    app.config["LLM_DAILY_LIMIT"] = 0
    assert usage.consume(3) is False


# ---- endpoint -----------------------------------------------------------------------------

def test_fit_endpoint_requires_login_and_validates(app):
    assert app.test_client().post("/opportunities/1/fit", json={"text": ME}).status_code == 401
    c = login(app)
    oid = opp().id
    assert c.post("/opportunities/999/fit", json={"text": ME}).status_code == 404
    url = f"/opportunities/{oid}/fit"
    assert c.post(url, json={}).status_code == 400
    assert c.post(url, json={"text": ME, "orcid": "0000-0002-1825-0097"}).status_code == 400
    assert c.post(url, json={"text": "too short"}).status_code == 400
    assert c.post(url, json={"text": "x" * 4001}).status_code == 400
    assert c.post(url, json={"orcid": "nope"}).status_code == 400


def test_fit_endpoint_happy_path_and_errors(app, monkeypatch):
    c = login(app)
    url = f"/opportunities/{opp().id}/fit"
    app.config["LLM_FAKE"] = FakeLLM(model())
    body = c.post(url, json={"text": ME}).get_json()
    assert body["summary"] == "Good fit." and body["downgraded"] == 2 and body["dropped_requirements"] == 2
    assert body["papers"][0]["id"] == "P1"

    app.config["LLM_FAKE"] = FakeLLM(error=LLMError("the AI service is rate limited or out of quota; try again later"))
    before = LlmUsage.query.one().count
    assert c.post(url, json={"text": ME}).status_code == 502
    assert LlmUsage.query.one().count == before  # the failed call was refunded

    monkeypatch.setattr(openalex, "works_by_orcid", lambda orcid, limit=10: ("Ann", [paper(7)]))
    app.config["LLM_FAKE"] = FakeLLM(model())
    assert c.post(url, json={"orcid": "0000-0002-1825-0097"}).status_code == 200
    assert "Imaging paper 7" in app.config["LLM_FAKE"].main[1]  # the profile came from the ORCID papers

    app.config["LLM_DAILY_LIMIT"] = 1
    assert c.post(url, json={"text": ME}).status_code == 429
    app.config["LLM_BACKEND"] = "openai"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert c.post(url, json={"text": ME}).status_code == 503
