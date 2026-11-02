from dataclasses import dataclass, field

from ..extensions import db
from ..models import Opportunity
from . import dense, fusion, lexical
from .clean import clean_text
from .filters import Filters
from .text import doc_text


@dataclass
class Hit:
    id: int
    external_id: str
    title: str
    agency: str | None
    status: str | None
    close_date: str | None
    url: str | None
    snippet: str
    amount_max: int | None
    score: float
    ranks: dict[str, int] = field(default_factory=dict)  # why it matched: rank in each retriever


def _snippet(abstract: str | None, n: int = 280) -> str:
    text = " ".join(clean_text(abstract).split())
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


def search(
    query: str,
    k: int = 10,
    filters: Filters | None = None,
    mode: str = "hybrid",  # bm25 | dense | hybrid
    rerank: bool | str = False,  # True = default model, or a name from rerank.MODELS
    depth: int = 100,
) -> list[Hit]:
    conditions = filters.conditions() if filters else []
    allowed = None
    if conditions:
        allowed = set(db.session.scalars(db.select(Opportunity.id).where(*conditions)))
    rankings: dict[str, list[int]] = {}
    if mode in ("bm25", "hybrid"):
        rankings["bm25"] = lexical.get_index().search(query, depth, allowed)
    if mode in ("dense", "hybrid"):
        rankings["dense"] = dense.search(query, depth, conditions)
    fused = fusion.rrf(rankings)[: max(k, depth if rerank else k)]
    if rerank and fused:
        by_id = {
            o.id: o for o in db.session.query(Opportunity).filter(Opportunity.id.in_([i for i, _ in fused]))
        }
        from .rerank import rerank as cross_encode

        fused = cross_encode(
            query,
            [(i, doc_text(by_id[i].title, by_id[i].abstract)) for i, _ in fused],
            **({} if rerank is True else {"model": rerank}),
        )
    fused = fused[:k]
    rows = {o.id: o for o in db.session.query(Opportunity).filter(Opportunity.id.in_([i for i, _ in fused]))}
    pos = {name: {d: r for r, d in enumerate(ranked, 1)} for name, ranked in rankings.items()}
    return [
        Hit(
            id=i, external_id=rows[i].external_id, title=rows[i].title, agency=rows[i].agency,
            status=rows[i].status, close_date=str(rows[i].close_date) if rows[i].close_date else None,
            url=rows[i].url, snippet=_snippet(rows[i].abstract),
            amount_max=rows[i].amount_max, score=score, ranks={n: p[i] for n, p in pos.items() if i in p},
        )
        for i, score in fused
    ]
