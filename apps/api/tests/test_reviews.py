import re
from datetime import timedelta

import pytest

from grantlens_api import create_app, jobs, reviews
from grantlens_api.config import TestConfig
from grantlens_api.extensions import db
from grantlens_api.literature import openalex
from grantlens_api.llm import LLMError
from grantlens_api.models import LlmUsage, Review
from grantlens_api.retrieval import embedder

PW = "correct horse battery"
FILLER = " The work is evaluated on several public datasets and compared with strong published baselines."
ABSTRACTS = {  # each is longer than reviews.MIN_ABSTRACT, as real abstracts are
    1: "We propose a convolutional network that segments brain tumors in MRI with high accuracy across sites." + FILLER,
    2: "This survey reviews transformer architectures for medical image segmentation and open benchmarks." + FILLER,
    3: "Federated learning lets hospitals train segmentation models without sharing patient scans at all." + FILLER,
    4: "A benchmark of loss functions for imbalanced tumor segmentation reveals large gaps between datasets." + FILLER,
}


def paper(i, abstract=None, title=None, authors=None):
    return openalex.Paper(
        id=f"W{i}", title=title or f"Segmentation paper {i}", year=2020 + i, cited_by=i * 10, doi=f"https://doi.org/10.1/{i}",
        abstract=ABSTRACTS.get(i, "x" * 200) if abstract is None else abstract,
        authors=authors if authors is not None else [f"Ann Author{i}", "Bo Lee"], venue="Journal of Imaging", url=f"https://doi.org/10.1/{i}",
    )


class FakeLLM:
    def __init__(self, result=None, error=None, queries=None, sentences=None, supported=None):
        self.result, self.error, self.queries, self.calls = result, error, queries or [], []
        self.sentences, self.supported = sentences, supported  # overrides for the summary and check steps

    def complete_json(self, system, user, schema, max_tokens=1500):
        self.calls.append((system, user, schema))
        if self.error:
            raise self.error
        if "queries" in schema["properties"]:
            return {"queries": self.queries}
        if system == reviews.SUMMARY_SYSTEM:  # default: one sentence per theme citing that theme's first paper
            if self.sentences is not None:
                return {"themes": self.sentences}
            blocks = re.findall(r'THEME (\d+): [^\n]*\n(P\d+): [^\n]*Quote: "([^"]+)"', user)
            return {"themes": [{"theme": int(i), "sentences": [
                {"text": f"{q}. [P99]", "papers": [p], "quote_paper": p, "quote": q}]} for i, p, q in blocks]}
        if system == reviews.CHECK_SYSTEM:  # default: everything supported
            keys = re.findall(r"SENTENCE (\S+):", user)
            return {"verdicts": [{"key": k, "reason": "nothing", "supported": self.supported is None or k in self.supported}
                                 for k in keys]}
        return self.result(user) if callable(self.result) else self.result

    @property
    def main(self):
        return self.calls[-1]


def good_result(**over):
    base = {
        "themes": [
            {"title": "Architectures", "summary": "Networks and transformers dominate [P1] [P2]. See also [P9].", "papers": ["P1", "P2", "P7"]},
            {"title": "Data and training", "summary": "Federated and loss-focused work [P3].", "papers": ["P3", "P1"]},
        ],
        "annotations": [
            {"paper": "P1", "annotation": "A CNN for brain tumors.", "evidence_quote": "segments brain tumors in MRI with high accuracy"},
            {"paper": "P2", "annotation": "A survey.", "evidence_quote": "reviews transformer architectures for medical image segmentation"},
            {"paper": "P3", "annotation": "Federated training.", "evidence_quote": "trains segmentation models on cloud GPUs"},  # invented
            {"paper": "P9", "annotation": "No such paper.", "evidence_quote": "anything at all here"},
        ],
        "open_questions": ["q1", "q2", "q3", "q4", "q5"],
    }
    return {**base, **over}


def followup_result(**over):
    base = {
        "themes": [{"title": "data and TRAINING", "summary": "ignored: theme exists", "papers": ["P4", "P3", "P1"]}],
        "annotations": [
            {"paper": "P3", "annotation": "Federated training.",
             "evidence_quote": "lets hospitals train segmentation models without sharing patient scans"},
            {"paper": "P4", "annotation": "A loss benchmark.", "evidence_quote": "reveals large gaps between datasets"},
            {"paper": "P1", "annotation": "must be ignored: P1 was not asked about", "evidence_quote": "segments brain tumors in MRI"},
        ],
        "open_questions": ["ignored: only the first request's questions are kept"],
    }
    return {**base, **over}


def two_step(first=None, second=None):
    """First request gets `first`; the follow-up (it says 'not been placed yet') gets `second`."""
    return lambda user: (second if second is not None else followup_result()) if "not been placed yet" in user \
        else (first if first is not None else good_result())


@pytest.fixture
def app(monkeypatch):
    app = create_app(TestConfig)
    app.config["LLM_FAKE"] = FakeLLM(two_step())
    papers = [paper(1), paper(2), paper(3), paper(4), paper(5, abstract="too short")]
    monkeypatch.setattr(openalex, "search_works", lambda q, limit, year_from: list(papers))
    monkeypatch.setattr(reviews, "_by_relevance", lambda ps, topic: ps)  # keep input order so P-ids are predictable
    with app.app_context():
        db.create_all()
        yield app


def build_review(client, **body):
    """POST /reviews (JOBS_MODE=sync runs the job inside the request) and return (response, finished job view)."""
    res = client.post("/reviews", json={"topic": "tumor segmentation", **body})
    job = res.get_json().get("job") if res.status_code == 202 else None
    return res, (client.get(f"/reviews/jobs/{job['id']}").get_json()["job"] if job else None)


def login(app, email="a@example.com"):
    c = app.test_client()
    assert c.post("/auth/register", json={"email": email, "password": PW}).status_code == 201
    return c


# ---- building -----------------------------------------------------------------------------

def test_build_verifies_annotations_themes_and_markers(app):
    r = reviews.build("tumor segmentation", FakeLLM(two_step()))
    by_id = {p["id"]: p for p in r.papers}
    assert by_id["P1"]["annotation"] == "A CNN for brain tumors." and by_id["P1"]["evidence_quote"]
    assert by_id["P1"]["theme"] == 0
    assert r.skipped_no_abstract == 1 and len(r.papers) == 4  # the 'too short' abstract was left out
    assert [t["title"] for t in r.themes] == ["Architectures", "Data and training"]  # no "Other": all placed
    assert r.themes[0]["papers"] == ["P1", "P2"]  # P1 stays in its first theme; P7 never existed
    assert r.themes[1]["papers"] == ["P3", "P4"]  # P4 joined the existing theme, matched by title ignoring case
    assert r.themes[0]["summary"] == "segments brain tumors in MRI with high accuracy. [P1]"  # rebuilt from the verified notes; the model's own markers go
    assert r.themes[1]["summary"] == "lets hospitals train segmentation models without sharing patient scans. [P3]"
    assert r.removed_citations == 2  # the P7 member and the [P9] marker (in the grouping step's own summary)
    assert r.unverified_annotations == 1  # P3's first, invented quote; its second attempt verified
    assert by_id["P3"]["annotation"] == "Federated training." and by_id["P4"]["annotation"] == "A loss benchmark."
    assert all(p["annotation"] for p in r.papers)
    assert len(r.open_questions) == 4 and "ignored" not in " ".join(r.open_questions)
    assert all(by_id[pid]["theme"] == i for i, t in enumerate(r.themes) for pid in t["papers"])


def test_followup_only_asks_about_missing_papers_and_names_existing_themes(app):
    llm = FakeLLM(two_step())
    reviews.build("tumor segmentation", llm)
    assert len(llm.calls) == 5  # queries, first request, follow-up, summaries, check
    first, follow = llm.calls[1][1], llm.calls[2][1]
    assert all(f"P{i}: " in first for i in (1, 2, 3, 4))
    assert "P3: " in follow and "P4: " in follow and "P1: " not in follow and "P2: " not in follow
    assert "Architectures; Data and training" in follow


def test_no_followup_when_the_first_answer_is_complete(app):
    full = good_result(
        themes=[{"title": "All", "summary": "s [P1]", "papers": ["P1", "P2", "P3", "P4"]}],
        annotations=[
            {"paper": "P1", "annotation": "a", "evidence_quote": "segments brain tumors in MRI with high accuracy"},
            {"paper": "P2", "annotation": "b", "evidence_quote": "reviews transformer architectures for medical image segmentation"},
            {"paper": "P3", "annotation": "c", "evidence_quote": "lets hospitals train segmentation models without sharing patient scans"},
            {"paper": "P4", "annotation": "d", "evidence_quote": "reveals large gaps between datasets"},
        ],
    )
    llm = FakeLLM(two_step(first=full))
    r = reviews.build("tumor segmentation", llm)
    assert len(llm.calls) == 4 and r.unverified_annotations == 0 and len(r.themes) == 1


def test_papers_the_model_never_places_land_in_other_and_bad_quotes_stay_blank(app):
    nothing = {"themes": [], "annotations": [{"paper": "P4", "annotation": "x", "evidence_quote": "made up words here"}],
               "open_questions": []}
    r = reviews.build("tumor segmentation", FakeLLM(two_step(second=nothing)))
    assert r.themes[-1]["title"] == reviews.OTHER and r.themes[-1]["papers"] == ["P4"]
    p4 = next(p for p in r.papers if p["id"] == "P4")
    assert p4["annotation"] == "" and p4["evidence_quote"] == "" and p4["theme"] == len(r.themes) - 1
    assert r.unverified_annotations == 2  # P3's first attempt and P4's invented quote


@pytest.mark.parametrize(("n_papers", "covered"), [(20, 20), (30, 24)])  # 3 passes x 8 papers = 24 at most
def test_followups_work_through_many_missing_papers_in_batches_then_stop(app, monkeypatch, n_papers, covered):
    many = [paper(i, abstract=f"Study number {i} reports finding {i} for segmentation. " + FILLER * 2, title=f"Paper {i}")
            for i in range(1, n_papers + 1)]
    monkeypatch.setattr(openalex, "search_works", lambda q, limit, year_from: list(many))

    def model(user):
        listed = [int(n) for n in re.findall(r"^P(\d+): ", user, re.MULTILINE)]
        if "not been placed yet" not in user:  # the first request returns almost nothing
            return {"themes": [], "annotations": [], "open_questions": ["q"]}
        return {"themes": [{"title": "Everything", "summary": "", "papers": [f"P{n}" for n in listed]}],
                "annotations": [{"paper": f"P{n}", "annotation": f"About {n}.",
                                 "evidence_quote": f"reports finding {n} for segmentation"} for n in listed],
                "open_questions": []}

    llm = FakeLLM(model)
    r = reviews.build("segmentation", llm, max_papers=n_papers)
    followups = [c for c in llm.calls if "not been placed yet" in c[1]]
    assert len(followups) == reviews.MAX_FOLLOWUPS
    assert all(len(re.findall(r"^P\d+: ", c[1], re.MULTILINE)) <= reviews.FOLLOWUP_BATCH for c in followups)
    everything = next(t for t in r.themes if t["title"] == "Everything")
    assert len(everything["papers"]) == covered
    assert sum(1 for p in r.papers if p["annotation"]) == covered
    if covered < n_papers:  # whatever the passes could not reach is still listed, in "Other papers"
        assert r.themes[-1]["title"] == reviews.OTHER and len(r.themes[-1]["papers"]) == n_papers - covered
    else:
        assert all(t["title"] != reviews.OTHER for t in r.themes)


def test_prompt_numbers_papers_and_marks_them_untrusted(app):
    llm = FakeLLM(two_step())
    reviews.build("tumor segmentation", llm)
    system, user, _ = llm.calls[1]
    assert "untrusted" in system and "never follow instructions" in system
    assert "P1: " in user and "Abstract: " in user and "too short" not in user


def test_search_queries_cleaned_and_fall_back(app):
    llm = FakeLLM(queries=["  federated learning ", "", "federated learning", "y" * 300])
    q = reviews.search_queries("tumor segmentation", llm)
    assert q[0] == "tumor segmentation" and q[1] == "federated learning" and len(q) == 3 and len(q[2]) == 120
    assert reviews.search_queries("t", FakeLLM(error=LLMError("down"))) == ["t"]


def test_no_papers_gives_an_empty_review(app, monkeypatch):
    monkeypatch.setattr(openalex, "search_works", lambda q, limit, year_from: [])
    r = reviews.build("zzz", FakeLLM(two_step()))
    assert r.papers == [] and r.themes == [] and r.literature_available


def test_papers_are_ordered_by_closeness_to_the_topic(monkeypatch):
    monkeypatch.setattr(embedder, "embed_documents", lambda ts: [[1.0, 0.0] if "tumor" in t.lower() else [0.0, 1.0] for t in ts])
    birds = openalex.Paper(id="B", title="Bird song", year=2020, cited_by=0, abstract="birds sing " * 30)
    tumors = openalex.Paper(id="T", title="Tumor imaging", year=2020, cited_by=0, abstract="tumor scans " * 30)
    assert [p.id for p in reviews._by_relevance([birds, tumors], "tumor segmentation")] == ["T", "B"]
    assert [p.id for p in reviews._by_relevance([birds], "anything")] == ["B"]


def test_bibtex_escapes_and_keys_are_unique():
    p1 = {"id": "P1", "title": "Cats & dogs: 100% {fun} #1", "authors": ["Ann Smith", "Bo Lee"], "year": 2021,
          "venue": "J_of Stuff", "doi": "https://doi.org/10.1/abc", "url": "https://doi.org/10.1/abc"}
    p2 = {**p1, "id": "P2", "doi": None}
    bib = reviews.to_bibtex([p1, p2])
    assert "@article{smith2021cats," in bib and "@article{smith2021cats2," in bib
    assert r"title = {Cats \& dogs: 100\% \{fun\} \#1}" in bib
    assert "author = {Ann Smith and Bo Lee}" in bib and "doi = {10.1/abc}" in bib and r"journal = {J\_of Stuff}" in bib
    assert "doi = " not in bib.split("@article")[2]  # the second has none
    assert "and others" in reviews.to_bibtex([{**p1, "authors": [f"A{i} B{i}" for i in range(20)]}])
    assert reviews.to_bibtex([{**p1, "authors": [], "year": None, "venue": None, "doi": None, "url": None}]).startswith("@article{anon")


def test_markdown_contains_themes_annotations_and_quotes(app):
    built = reviews.build("tumor segmentation", FakeLLM(two_step()))
    from dataclasses import asdict

    md = reviews.to_markdown("tumor segmentation", asdict(built))
    assert md.startswith("# Literature review: tumor segmentation") and "## Architectures" in md
    assert "A CNN for brain tumors." in md and '> "segments brain tumors in MRI with high accuracy"' in md
    assert "## Open questions" in md and "read the papers before citing them" in md


# ---- endpoints ----------------------------------------------------------------------------

def test_create_get_list_export_delete(app):
    c = login(app)
    res, job = build_review(c)
    assert res.status_code == 202 and job["status"] == "done" and job["error"] is None
    rid = job["review_id"]
    body = c.get(f"/reviews/{rid}").get_json()
    assert body["themes"][0]["title"] == "Architectures" and len(body["papers"]) == 4
    assert c.get(f"/reviews/{rid}").get_json()["topic"] == "tumor segmentation"
    assert c.get("/reviews").get_json()["reviews"][0]["papers"] == 4
    bib = c.get(f"/reviews/{rid}.bib")
    assert bib.mimetype == "application/x-bibtex" and b"@article{" in bib.data and "review-" in bib.headers["Content-Disposition"]
    md = c.get(f"/reviews/{rid}.md")
    assert md.mimetype == "text/markdown" and b"## Architectures" in md.data
    assert c.delete(f"/reviews/{rid}").status_code == 204
    assert c.get(f"/reviews/{rid}").status_code == 404 and Review.query.count() == 0


def test_validation_and_failures(app, monkeypatch):
    assert app.test_client().post("/reviews", json={"topic": "tumor"}).status_code == 401
    c = login(app)
    assert c.post("/reviews", json={"topic": "ab"}).status_code == 400
    assert c.post("/reviews", json={"topic": "x" * 301}).status_code == 400
    assert c.post("/reviews", json={"topic": "valid topic", "year_from": "2019"}).status_code == 400
    assert c.post("/reviews", json={"topic": "valid topic", "year_from": 1800}).status_code == 400
    assert c.post("/reviews", json={"topic": "valid topic", "max_papers": 3}).status_code == 400
    assert c.post("/reviews", json={"topic": "valid topic", "max_papers": 99}).status_code == 400

    app.config["LLM_FAKE"] = FakeLLM(error=LLMError("the AI service is rate limited or out of quota; try again later"))
    res, job = build_review(c, topic="valid topic")
    assert res.status_code == 202 and job["status"] == "failed" and "rate limited" in job["error"]
    assert LlmUsage.query.one().count == 0  # refunded

    app.config["LLM_FAKE"] = FakeLLM(two_step())
    monkeypatch.setattr(openalex, "search_works", lambda q, limit, year_from: [])
    _, job = build_review(c, topic="valid topic")
    assert job["status"] == "failed" and "broader words" in job["error"] and LlmUsage.query.one().count == 0

    def down(q, limit, year_from):
        raise openalex.OpenAlexError("boom")

    monkeypatch.setattr(openalex, "search_works", down)
    _, job = build_review(c, topic="valid topic")
    assert job["status"] == "failed" and "could not be reached" in job["error"] and LlmUsage.query.one().count == 0

    app.config["LLM_BACKEND"] = "openai"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert c.post("/reviews", json={"topic": "valid topic"}).status_code == 503


def test_limits_and_privacy(app, monkeypatch):
    from grantlens_api.blueprints import reviews as bp

    a, b = login(app), login(app, "b@example.com")
    rid = build_review(a)[1]["review_id"]
    assert b.get("/reviews").get_json()["reviews"] == []
    for url in (f"/reviews/{rid}", f"/reviews/{rid}.bib", f"/reviews/{rid}.md"):
        assert b.get(url).status_code == 404
    assert b.delete(f"/reviews/{rid}").status_code == 404 and len(a.get("/reviews").get_json()["reviews"]) == 1
    monkeypatch.setattr(bp, "MAX_REVIEWS", 1)
    assert a.post("/reviews", json={"topic": "another topic"}).status_code == 409
    monkeypatch.setattr(bp, "MAX_REVIEWS", 20)
    app.config["LLM_DAILY_LIMIT"] = 1
    assert build_review(b)[1]["status"] == "done"
    assert b.post("/reviews", json={"topic": "tumor again"}).status_code == 429


def sentence(text, papers, quote_paper=None, quote="segments brain tumors in MRI with high accuracy"):
    return {"text": text, "papers": papers, "quote_paper": quote_paper or papers[0], "quote": quote}


def test_summary_sentences_must_cite_the_themes_papers_and_pass_the_check(app):
    sentences = [
        {"theme": 0, "sentences": [
            sentence("P1 segments tumors [P1].", ["P1"]),
            sentence("Cites a paper from another theme.", ["P3"]),  # P3 is not in theme 0
        ]},
        {"theme": 1, "sentences": [
            sentence("Lets hospitals train segmentation models.", ["P3"], quote="lets hospitals train segmentation models"),
            sentence("Reveals large gaps between datasets.", ["P4"], quote="reveals large gaps between datasets"),
        ]},
        {"theme": 7, "sentences": [sentence("No such theme.", ["P1"])]},
    ]
    llm = FakeLLM(two_step(), sentences=sentences, supported={"0.0", "1.0"})  # "Overreach." (1.1) fails the check
    r = reviews.build("tumor segmentation", llm)
    assert r.themes[0]["summary"] == "P1 segments tumors. [P1]"  # the model's own marker is stripped and re-added
    assert r.themes[1]["summary"] == "Lets hospitals train segmentation models. [P3]"
    assert r.dropped_summary_sentences == 2  # the wrong-theme citation and the failed check; an unknown theme is just skipped
    check = llm.calls[-1]
    assert "P1 abstract: " in check[1] and "untrusted" in check[0] and "when unsure" in check[0]


def test_a_summary_sentence_needs_a_real_quote_from_its_own_papers_and_grounded_words(app):
    ok = sentence("Segments brain tumors in MRI with high accuracy.", ["P1"])
    invented = sentence("Segments brain tumors.", ["P1"], quote="outperforms every radiologist")  # not in P1
    other_paper = sentence("Segments brain tumors.", ["P1"], quote_paper="P2")  # P2 is not the cited paper
    two_papers = sentence("Segments brain tumors in MRI with high accuracy.", ["P1", "P2"])  # one paper per sentence
    extra_detail = sentence("Segments brain tumors in MRI with high accuracy across public datasets worldwide.", ["P1"])
    number = sentence("Segments brain tumors in 97% of cases.", ["P1"])  # no 97 in the abstract
    ungrounded = sentence("Revolutionised oncology pipelines worldwide dramatically.", ["P1"])
    llm = FakeLLM(two_step(), sentences=[{"theme": 0, "sentences": [ok, invented]},
                                         {"theme": 1, "sentences": [number, ungrounded]}])
    r = reviews.build("tumor segmentation", llm)
    assert r.themes[0]["summary"] == "Segments brain tumors in MRI with high accuracy. [P1]"
    assert r.themes[1]["summary"] == "" and r.dropped_summary_sentences == 3 + 2  # theme 1 got one repair round too
    assert reviews.quote_is_verbatim("with high accuracy", ABSTRACTS[1])
    llm = FakeLLM(two_step(), sentences=[{"theme": 0, "sentences": [other_paper, two_papers]},
                                         {"theme": 1, "sentences": [extra_detail]}])
    built = reviews.build("tumor segmentation", llm)
    assert [t["summary"] for t in built.themes] == ["", ""] and built.dropped_summary_sentences == 3 + 3


def test_grounded_compares_numbers_exactly_and_words_by_stem():
    src = ["Segmentation networks improved accuracy by 12.5 percent across hospitals."]
    assert reviews.grounded("Segmentation networks improve accuracy across hospital sites.", src)
    assert not reviews.grounded("Accuracy improved by 12 percent.", ["Accuracy improved by 7 percent."])
    assert not reviews.grounded("Networks improved accuracy by 13 percent.", src)
    assert not reviews.grounded("Quantum blockchain disrupts everything universally.", src)


def test_a_failed_summary_step_leaves_no_summary_not_an_unchecked_one(app, monkeypatch):
    llm = FakeLLM(two_step())
    real = llm.complete_json

    def flaky(system, user, schema, max_tokens=1500):
        if system == reviews.CHECK_SYSTEM:
            raise LLMError("down")
        return real(system, user, schema, max_tokens)

    llm.complete_json = flaky
    r = reviews.build("tumor segmentation", llm)
    assert [t["summary"] for t in r.themes] == ["", ""] and all(p["annotation"] for p in r.papers)


# ---- background jobs ----------------------------------------------------------------------

def test_a_job_can_only_be_polled_by_its_owner_and_failures_show_in_the_list(app, monkeypatch):
    a, b = login(app), login(app, "b@example.com")
    monkeypatch.setattr(openalex, "search_works", lambda q, limit, year_from: [])
    _, job = build_review(a)
    assert job["status"] == "failed"
    assert b.get(f"/reviews/jobs/{job['id']}").status_code == 404 and a.get("/reviews/jobs/999").status_code == 404
    listing = a.get("/reviews").get_json()
    assert listing["reviews"] == [] and [p["error"] is not None for p in listing["pending"]] == [True]
    assert b.get("/reviews").get_json()["pending"] == []


def test_worker_mode_queues_and_the_worker_runs_it_once(app):
    app.config["JOBS_MODE"] = "worker"
    c = login(app)
    res, job = build_review(c)
    assert res.status_code == 202 and job["status"] == "queued" and job["review_id"] is None
    assert c.get("/reviews").get_json()["pending"][0]["status"] == "queued"
    assert jobs.work(app, once=True) == 1 and jobs.work(app, once=True) == 0  # nothing left for a second pass
    done = c.get(f"/reviews/jobs/{job['id']}").get_json()["job"]
    assert done["status"] == "done" and c.get(f"/reviews/{done['review_id']}").status_code == 200
    assert c.get("/reviews").get_json()["pending"] == []


def test_only_one_worker_can_claim_a_job(app):
    app.config["JOBS_MODE"] = "worker"
    build_review(login(app))
    first, second = jobs.claim(), jobs.claim()
    assert first is not None and first.status == "running" and second is None


def test_two_active_jobs_per_user_and_a_crashed_worker_is_reaped_and_refunded(app):
    app.config["JOBS_MODE"] = "worker"
    c = login(app)
    assert build_review(c)[0].status_code == 202 and build_review(c)[0].status_code == 202
    third = build_review(c)[0]
    assert third.status_code == 409 and "already being built" in third.get_json()["error"]
    assert LlmUsage.query.one().count == 2  # the refused third did not use an AI request
    job = jobs.claim()  # a worker takes it and dies
    assert jobs.reap() == 0
    later = job.started_at.replace(tzinfo=None) + jobs.STALE_AFTER + timedelta(seconds=1)
    assert jobs.reap(now=later) == 1
    db.session.refresh(job)
    assert job.status == "failed" and "too long" in job.error and LlmUsage.query.one().count == 1


def test_a_crash_inside_a_job_is_recorded_and_refunded_not_left_running(app, monkeypatch):
    c = login(app)

    def boom(*a, **k):
        raise RuntimeError("bug")

    monkeypatch.setattr(reviews, "build", boom)
    _, job = build_review(c)
    assert job["status"] == "failed" and "something went wrong" in job["error"]
    assert LlmUsage.query.one().count == 0


def test_thread_mode_finishes_in_the_background(app):
    import time

    app.config["JOBS_MODE"] = "thread"
    c = login(app)
    res = c.post("/reviews", json={"topic": "tumor segmentation"})
    jid = res.get_json()["job"]["id"]
    for _ in range(100):
        job = c.get(f"/reviews/jobs/{jid}").get_json()["job"]
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert job["status"] == "done"


def test_a_theme_whose_sentences_were_all_rejected_gets_one_repair_round(app):
    bad = sentence("Revolutionised oncology pipelines worldwide dramatically.", ["P1"])
    good = sentence("Segments brain tumors in MRI with high accuracy.", ["P1"])
    llm = FakeLLM(two_step())
    answers = iter([[{"theme": 0, "sentences": [bad]}, {"theme": 1, "sentences": [bad]}],
                    [{"theme": 0, "sentences": [good]}]])  # the repair round only has to fix theme 0 (1 stays empty)
    real = llm.complete_json

    def scripted(system, user, schema, max_tokens=1500):
        if system == reviews.SUMMARY_SYSTEM:
            llm.sentences = next(answers)
            llm.calls.append(("summary-prompt", user, None))
        return real(system, user, schema, max_tokens)

    llm.complete_json = scripted
    r = reviews.build("tumor segmentation", llm)
    prompts = [c[1] for c in llm.calls if c[0] == "summary-prompt"]
    assert len(prompts) == 2 and reviews.RETRY_NOTE in prompts[1] and "THEME 1" in prompts[1] and "THEME 0" in prompts[1]
    assert r.themes[0]["summary"] == "Segments brain tumors in MRI with high accuracy. [P1]" and r.themes[1]["summary"] == ""
