from collections.abc import Iterator
from datetime import date, datetime, timedelta

import httpx

from .base import NormalizedAward
from .windows import windows

API = "https://api.reporter.nih.gov/v2/projects/search"
PAGE = 500
FIELDS = [
    "ApplId", "ProjectNum", "ProjectTitle", "AbstractText", "Organization", "AgencyIcAdmin",
    "AwardAmount", "ProjectStartDate", "ProjectEndDate", "PrincipalInvestigators", "Terms",
    "FiscalYear", "ProjectDetailUrl",
]


def _date(value: str | None) -> date | None:
    try:
        return datetime.fromisoformat(value).date() if value else None
    except ValueError:
        return None


def normalize(r: dict) -> NormalizedAward:
    terms = [t for t in (r.get("terms") or "").replace("><", "|").strip("<>").split("|") if t]
    pis = [p.get("full_name") for p in r.get("principal_investigators") or [] if p.get("full_name")]
    return NormalizedAward(
        source="nih_reporter",
        external_id=str(r["appl_id"]),
        project_number=r.get("project_num"),
        title=(r.get("project_title") or "").strip(),
        abstract=(r.get("abstract_text") or "").strip() or None,
        agency=(r.get("agency_ic_admin") or {}).get("name"),
        organization=(r.get("organization") or {}).get("org_name"),
        investigators=pis,
        keywords=sorted(set(terms)),
        amount=r.get("award_amount"),
        fiscal_year=r.get("fiscal_year"),
        start_date=_date(r.get("project_start_date")),
        end_date=_date(r.get("project_end_date")),
        url=r.get("project_detail_url"),
        raw=r,
    )


class NihReporterSource:
    name = "nih_reporter"

    def __init__(self, text: str | None = None, since: date | None = None,
                 until: date | None = None):
        self.text = text
        self.until = until or date.today()
        self.since = since or self.until - timedelta(days=365)

    def fetch(self, limit: int | None = None) -> Iterator[NormalizedAward]:
        seen: set[str] = set()
        with httpx.Client(timeout=60) as client:
            for start, end in windows(self.since, self.until, days=7):
                criteria: dict = {
                    "award_notice_date": {"from_date": start.isoformat(),
                                          "to_date": end.isoformat()},
                }
                if self.text:
                    criteria["advanced_text_search"] = {
                        "operator": "and", "search_field": "all", "search_text": self.text,
                    }
                offset = 0
                while offset < 14999:  # RePORTER caps paging at 15k per query; weeks stay below
                    body = {"criteria": criteria, "offset": offset, "limit": PAGE,
                            "include_fields": FIELDS, "sort_field": "ApplId", "sort_order": "asc"}
                    data = client.post(API, json=body).raise_for_status().json()
                    results = data.get("results") or []
                    for r in results:
                        if str(r["appl_id"]) in seen:
                            continue
                        if limit is not None and len(seen) >= limit:
                            return
                        seen.add(str(r["appl_id"]))
                        yield normalize(r)
                    offset += len(results)
                    if not results or offset >= data["meta"]["total"]:
                        break
