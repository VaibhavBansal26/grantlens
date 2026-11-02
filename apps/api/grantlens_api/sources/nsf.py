from collections.abc import Iterator
from datetime import date, datetime

import httpx

from .base import NormalizedAward

API = "https://api.nsf.gov/services/v1/awards.json"
PAGE = 25  # NSF returns at most 25 per request
FIELDS = (
    "id,title,abstractText,awardeeName,fundsObligatedAmt,startDate,expDate,piFirstName,"
    "piLastName,fundProgramName,agency,date"
)


def _date(value: str | None) -> date | None:
    try:
        return datetime.strptime(value, "%m/%d/%Y").date() if value else None
    except ValueError:
        return None


def normalize(r: dict) -> NormalizedAward:
    start = _date(r.get("startDate"))
    pi = " ".join(p for p in (r.get("piFirstName"), r.get("piLastName")) if p)
    try:
        amount = int(r["fundsObligatedAmt"])
    except (KeyError, ValueError):
        amount = None
    return NormalizedAward(
        source="nsf",
        external_id=str(r["id"]),
        project_number=str(r["id"]),
        title=(r.get("title") or "").strip(),
        abstract=(r.get("abstractText") or "").strip() or None,
        agency=r.get("agency") or "NSF",
        organization=r.get("awardeeName"),
        investigators=[pi] if pi else [],
        keywords=[r["fundProgramName"]] if r.get("fundProgramName") else [],
        amount=amount,
        fiscal_year=start.year if start else None,
        start_date=start,
        end_date=_date(r.get("expDate")),
        url=f"https://www.nsf.gov/awardsearch/showAward?AWD_ID={r['id']}",
        raw=r,
    )


class NsfSource:
    name = "nsf"

    def __init__(self, keyword: str = "", date_start: str | None = None):
        self.keyword, self.date_start = keyword, date_start  # date_start: MM/DD/YYYY

    def fetch(self, limit: int | None = None) -> Iterator[NormalizedAward]:
        params = {"printFields": FIELDS, "rpp": PAGE, "offset": 1}
        if self.keyword:
            params["keyword"] = self.keyword
        if self.date_start:
            params["dateStart"] = self.date_start
        seen = 0
        with httpx.Client(timeout=60) as client:
            while True:
                res = client.get(API, params=params).raise_for_status().json()
                awards = res.get("response", {}).get("award") or []
                for r in awards:
                    if limit is not None and seen >= limit:
                        return
                    yield normalize(r)
                    seen += 1
                if len(awards) < PAGE:
                    return
                params["offset"] += PAGE
