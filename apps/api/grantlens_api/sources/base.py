from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


@dataclass
class NormalizedOpportunity:
    source: str
    external_id: str
    title: str
    number: str | None = None
    abstract: str | None = None
    agency: str | None = None
    categories: list[str] = field(default_factory=list)
    eligibility: list[str] = field(default_factory=list)
    funding_instruments: list[str] = field(default_factory=list)
    amount_min: int | None = None
    amount_max: int | None = None
    open_date: date | None = None
    close_date: date | None = None
    status: str | None = None
    url: str | None = None
    raw: dict = field(default_factory=dict)


class Source(Protocol):
    name: str

    def fetch(self, limit: int | None = None) -> Iterator[NormalizedOpportunity]: ...
