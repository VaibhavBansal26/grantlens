import time
from collections.abc import Iterator
from datetime import date, datetime

import httpx

from .base import NormalizedOpportunity

API = "https://api.grants.gov/v1/api"
PAGE = 100


def parse_date(value: str | None) -> date | None:
    for fmt in ("%m/%d/%Y", "%b %d, %Y %I:%M:%S %p %Z", "%Y-%m-%d"):
        try:
            return datetime.strptime((value or "").strip(), fmt).date()
        except ValueError:
            continue
    return None


def _int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def normalize(hit: dict, detail: dict | None) -> NormalizedOpportunity:
    d = detail or {}
    syn = d.get("synopsis") or d.get("forecast") or {}
    return NormalizedOpportunity(
        source="grants_gov",
        external_id=str(hit["id"]),
        number=hit.get("number"),
        title=hit["title"].strip(),
        abstract=(syn.get("synopsisDesc") or syn.get("forecastDesc") or "").strip() or None,
        agency=hit.get("agency") or syn.get("agencyName"),
        categories=sorted({c["description"] for c in syn.get("fundingActivityCategories") or []}),
        eligibility=sorted({a["description"] for a in syn.get("applicantTypes") or []}),
        funding_instruments=sorted({f["description"] for f in syn.get("fundingInstruments") or []}),
        amount_min=_int(syn.get("awardFloor")),
        amount_max=_int(syn.get("awardCeiling")),
        open_date=parse_date(hit.get("openDate")),
        close_date=parse_date(hit.get("closeDate")),
        status=hit.get("oppStatus"),
        url=f"https://www.grants.gov/search-results-detail/{hit['id']}",
        raw={"hit": hit, "detail": detail},
    )


class GrantsGovSource:
    name = "grants_gov"

    def __init__(self, statuses: str = "forecasted|posted", keyword: str = "", delay: float = 0.2):
        self.statuses, self.keyword, self.delay = statuses, keyword, delay

    def fetch(self, limit: int | None = None) -> Iterator[NormalizedOpportunity]:
        with httpx.Client(timeout=30) as client:
            start, seen = 0, 0
            while True:
                body = {
                    "rows": PAGE,
                    "startRecordNum": start,
                    "keyword": self.keyword,
                    "oppStatuses": self.statuses,
                }
                data = client.post(f"{API}/search2", json=body).raise_for_status().json()["data"]
                hits = data.get("oppHits") or []
                for hit in hits:
                    if limit is not None and seen >= limit:
                        return
                    detail = self._detail(client, hit["id"])
                    yield normalize(hit, detail)
                    seen += 1
                start += len(hits)
                if not hits or start >= data.get("hitCount", 0):
                    return

    def _detail(self, client: httpx.Client, opp_id: str) -> dict | None:
        time.sleep(self.delay)
        try:
            res = client.post(f"{API}/fetchOpportunity", json={"opportunityId": int(opp_id)})
            return res.raise_for_status().json().get("data")
        except httpx.HTTPError:
            return None
