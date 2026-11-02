from collections.abc import Iterator
from datetime import date, timedelta


def windows(since: date, until: date, days: int = 7) -> Iterator[tuple[date, date]]:
    """Fixed, non-overlapping date windows: stable paging unlike relevance-sorted queries."""
    start = since
    while start <= until:
        end = min(start + timedelta(days=days - 1), until)
        yield start, end
        start = end + timedelta(days=1)
