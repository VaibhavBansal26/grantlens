import pytest

from grantlens_api import create_app
from grantlens_api.config import TestConfig
from grantlens_api.extensions import db
from grantlens_api.ingest import upsert
from grantlens_api.literature import openalex
from grantlens_api.models import Opportunity
from grantlens_api.retrieval import dense, embedder
from grantlens_api.sources.base import NormalizedOpportunity as N

WORK = {
    "id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/abc", "title": " Deep learning for tumor imaging ",
    "publication_year": 2023, "cited_by_count": 12,
    "abstract_inverted_index": {"We": [0], "segment": [1], "tumors": [2], "with": [3], "AI": [4]},
    "authorships": [{"author": {"display_name": "Ann Lee"}}, {"author": {}}],
    "primary_location": {"source": {"display_name": "Nature Methods"}},
}


@pytest.fixture
def app(monkeypatch):
    app = create_app(TestConfig)
    monkeypatch.setattr(dense, "search", lambda q, k, c: [])  # pgvector needs Postgres
    openalex._cache.clear()
    with app.app_context():
        db.create_all()
        upsert([
            N("s", "1", "Cancer imaging AI", abstract="tumor segmentation deep learning", status="posted"),
            N("s", "2", "Rural health access", abstract="behavioral health", status="posted"),
            N("s", "3", "Archived imaging", abstract="tumor imaging", status="archived"),
        ])
        yield app


def test_rebuild_abstract_and_normalize():
    assert openalex.rebuild_abstract({"b": [1], "a": [0]}) == "a b"
    assert openalex.rebuild_abstract(None) == ""
    p = openalex.normalize(WORK)
    assert p.title == "Deep learning for tumor imaging" and p.abstract == "We segment tumors with AI"
    assert p.authors == ["Ann Lee"] and p.venue == "Nature Methods" and p.id == "W1"
    assert openalex.normalize({**WORK, "title": None}) is None


def test_duplicates_are_dropped():
    preprint = {**WORK, "id": "https://openalex.org/W2"}  # same DOI: the preprint of the same paper
    distinct = {**WORK, "id": "https://openalex.org/W3", "doi": None, "title": "Other"}
    out = openalex._papers([WORK, preprint, distinct])
    assert [p.title for p in out] == ["Deep learning for tumor imaging", "Other"]


def test_search_and_orcid_requests(monkeypatch):
    calls = []

    def fake(path, params):
        calls.append((path, params))
        if path.startswith("/authors"):
            return {"id": "https://openalex.org/A9", "display_name": "Ann Lee"}
        return {"results": [WORK]}

    monkeypatch.setattr(openalex, "_get", fake)
    assert openalex.search_works("ai", limit=3, year_from=2020)[0].title.startswith("Deep")
    assert calls[0][1]["filter"] == "from_publication_date:2020-01-01"
    name, papers = openalex.works_by_orcid("0000-0002-1825-0097")
    assert name == "Ann Lee" and len(papers) == 1
    assert calls[-1][1]["filter"] == "author.id:A9"
    with pytest.raises(ValueError):
        openalex.works_by_orcid("not-an-orcid")


def test_literature_endpoint(app, monkeypatch):
    c = app.test_client()
    assert c.get("/literature/search").status_code == 400
    assert c.get("/literature/search?q=" + "x" * 301).status_code == 400
    monkeypatch.setattr(openalex, "search_works", lambda q, limit, year_from: [openalex.normalize(WORK)])
    assert c.get("/literature/search?q=ai").get_json()["results"][0]["doi"] == "https://doi.org/10.1/abc"

    def down(*a, **k):
        raise openalex.OpenAlexError("OpenAlex request failed: ConnectError")

    monkeypatch.setattr(openalex, "search_works", down)
    assert c.get("/literature/search?q=ai").status_code == 502


def test_match_validation(app):
    c = app.test_client()
    assert c.post("/match", json={}).status_code == 400
    assert c.post("/match", json={"text": "a", "orcid": "0000-0002-1825-0097"}).status_code == 400
    assert c.post("/match", json={"text": "x" * 8001}).status_code == 400
    assert c.post("/match", json={"text": "tumor", "status": ["bogus"]}).status_code == 400
    assert c.post("/match", json={"orcid": "nope"}).status_code == 400


def test_match_from_text_defaults_to_open_grants(app):
    res = app.test_client().post("/match", json={"text": "tumor segmentation with deep learning"})
    titles = [r["title"] for r in res.get_json()["results"]]
    assert titles[0] == "Cancer imaging AI" and "Archived imaging" not in titles
    archived = app.test_client().post("/match", json={"text": "tumor imaging", "status": ["archived"]})
    assert [r["title"] for r in archived.get_json()["results"]] == ["Archived imaging"]


def test_match_from_orcid_reports_closest_paper(app, monkeypatch):
    paper = openalex.normalize(WORK)
    other = openalex.Paper(id="W2", title="Rural clinics", year=2020, cited_by=1, abstract="access")
    monkeypatch.setattr(openalex, "works_by_orcid", lambda orcid, limit=10: ("Ann Lee", [paper, other]))
    vecs = {"Deep": [1.0, 0.0], "Rural": [0.0, 1.0]}
    monkeypatch.setattr(embedder, "embed_documents",
                        lambda texts: [vecs["Deep" if t.startswith("Deep") else "Rural"] for t in texts])
    Opportunity.query.filter_by(external_id="1").one().embedding = [0.9, 0.1]
    Opportunity.query.filter_by(external_id="2").one().embedding = [0.1, 0.9]
    db.session.commit()
    body = app.test_client().post("/match", json={"orcid": "0000-0002-1825-0097"}).get_json()
    assert body["profile"]["name"] == "Ann Lee" and len(body["profile"]["papers"]) == 2
    by_title = {r["title"]: r["closest_paper"] for r in body["results"]}
    assert by_title["Cancer imaging AI"] == "Deep learning for tumor imaging"
    assert by_title["Rural health access"] == "Rural clinics"


def test_orcid_without_papers(app, monkeypatch):
    monkeypatch.setattr(openalex, "works_by_orcid", lambda orcid, limit=10: ("Ann Lee", []))
    assert app.test_client().post("/match", json={"orcid": "0000-0002-1825-0097"}).status_code == 404


def test_profile_text_is_bounded_and_title_first():
    from grantlens_api.match import PROFILE_CHARS, profile_text

    papers = [openalex.Paper(id=str(i), title=f"Title {i}", year=2020, cited_by=0, abstract="word " * 200)
              for i in range(10)]
    text = profile_text(papers)
    assert len(text) <= PROFILE_CHARS and text.startswith("Title 0. Title 1")
