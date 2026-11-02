"""Thin OpenAlex client (https://docs.openalex.org). No key needed; an email opts into the polite pool."""
import os
import re
import threading
import time
from dataclasses import dataclass, field

import httpx

BASE = "https://api.openalex.org"
FIELDS = "id,doi,title,publication_year,cited_by_count,abstract_inverted_index,authorships,primary_location"
ORCID = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
TTL = 600


class OpenAlexError(RuntimeError):
    pass


@dataclass
class Paper:
    id: str
    title: str
    year: int | None
    cited_by: int
    doi: str | None = None
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    venue: str | None = None
    url: str | None = None


def rebuild_abstract(inverted: dict[str, list[int]] | None) -> str:
    """OpenAlex ships abstracts as {word: [positions]}; put the words back in order."""
    if not inverted:
        return ""
    slots: dict[int, str] = {}
    for word, positions in inverted.items():
        for p in positions:
            slots[p] = word
    return " ".join(slots[i] for i in sorted(slots))


def normalize(work: dict) -> Paper | None:
    title = (work.get("title") or "").strip()
    if not title:
        return None
    source = ((work.get("primary_location") or {}).get("source") or {})
    doi = work.get("doi")
    return Paper(
        id=work["id"].rsplit("/", 1)[-1],
        title=title,
        year=work.get("publication_year"),
        cited_by=work.get("cited_by_count") or 0,
        doi=doi,
        abstract=rebuild_abstract(work.get("abstract_inverted_index")),
        authors=[a["author"]["display_name"] for a in (work.get("authorships") or [])[:6]
                 if a.get("author", {}).get("display_name")],
        venue=source.get("display_name"),
        url=doi or work["id"],
    )


_cache: dict[tuple, tuple[float, object]] = {}
_lock = threading.Lock()


def _get(path: str, params: dict) -> dict:
    key = (path, tuple(sorted(params.items())))
    with _lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < TTL:
            return hit[1]
    if mailto := os.environ.get("OPENALEX_EMAIL"):
        params = {**params, "mailto": mailto}
    try:
        res = httpx.get(f"{BASE}{path}", params=params, timeout=20)
        res.raise_for_status()
    except httpx.HTTPError as e:
        raise OpenAlexError(f"OpenAlex request failed: {e.__class__.__name__}") from e
    data = res.json()
    with _lock:
        if len(_cache) > 200:
            _cache.clear()
        _cache[key] = (time.monotonic(), data)
    return data


def _papers(results: list[dict]) -> list[Paper]:
    seen, out = set(), []
    for w in results:
        p = normalize(w)
        key = (p.doi or p.title.lower()) if p else None
        if p and key not in seen:  # OpenAlex lists some papers twice (preprint + journal)
            seen.add(key)
            out.append(p)
    return out


def search_works(query: str, limit: int = 10, year_from: int | None = None) -> list[Paper]:
    params = {"search": query, "per-page": min(limit, 25), "select": FIELDS}
    if year_from:
        params["filter"] = f"from_publication_date:{year_from}-01-01"
    return _papers(_get("/works", params)["results"])[:limit]


def works_by_orcid(orcid: str, limit: int = 10) -> tuple[str, list[Paper]]:
    """Author name and their most-cited recent works. Raises ValueError for a malformed ORCID iD."""
    if not ORCID.match(orcid):
        raise ValueError("ORCID iD should look like 0000-0002-1825-0097")
    author = _get(f"/authors/orcid:{orcid}", {"select": "id,display_name"})
    works = _get("/works", {
        "filter": f"author.id:{author['id'].rsplit('/', 1)[-1]}",
        "sort": "cited_by_count:desc", "per-page": min(limit * 2, 50), "select": FIELDS,
    })["results"]
    return author["display_name"], _papers(works)[:limit]
