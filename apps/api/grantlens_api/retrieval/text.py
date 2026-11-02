def doc_text(title: str, abstract: str | None, max_chars: int = 2000) -> str:
    """The text we index/embed for an opportunity (matches the eval baselines)."""
    return f"{title}. {abstract or ''}"[:max_chars]
