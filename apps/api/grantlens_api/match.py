"""Match a researcher's work (pasted text or an ORCID's papers) to funding opportunities."""
from dataclasses import asdict, dataclass

import numpy as np

from .extensions import db
from .literature import openalex
from .models import Opportunity
from .retrieval.filters import Filters
from .retrieval.service import Hit, search

MAX_TEXT = 8000
PROFILE_CHARS = 1800
OPEN_STATUSES = ["posted", "forecasted"]


@dataclass
class Match:
    hit: Hit
    closest_paper: str | None = None  # title of the profile paper most similar to this grant


def profile_text(papers: list[openalex.Paper]) -> str:
    """Titles lead (they carry the topic); abstracts fill the remaining budget."""
    parts = [p.title for p in papers]
    budget = PROFILE_CHARS - sum(len(t) + 2 for t in parts)
    for p in papers:
        if budget <= 0:
            break
        snippet = p.abstract[: min(300, budget)]
        parts.append(snippet)
        budget -= len(snippet)
    return ". ".join(s for s in parts if s)[:PROFILE_CHARS]


def match_grants(text: str, papers: list[openalex.Paper] | None = None, k: int = 15,
                 statuses: list[str] | None = None, mode: str = "hybrid") -> list[Match]:
    hits = search(text[:PROFILE_CHARS], k=k, filters=Filters(status=statuses or OPEN_STATUSES),
                  mode=mode)
    closest = _closest_papers(hits, papers) if papers else {}
    return [Match(h, closest.get(h.id)) for h in hits]


def _closest_papers(hits: list[Hit], papers: list[openalex.Paper]) -> dict[int, str]:
    from .retrieval.embedder import embed_documents

    rows = db.session.query(Opportunity.id, Opportunity.embedding).filter(
        Opportunity.id.in_([h.id for h in hits]), Opportunity.embedding.is_not(None)
    ).all()
    if not rows:
        return {}
    paper_vecs = np.array(embed_documents([f"{p.title}. {p.abstract}"[:1500] for p in papers]))
    out = {}
    for opp_id, emb in rows:
        sims = paper_vecs @ np.array(emb)
        out[opp_id] = papers[int(np.argmax(sims))].title
    return out


def as_json(m: Match) -> dict:
    return {**asdict(m.hit), "closest_paper": m.closest_paper}
