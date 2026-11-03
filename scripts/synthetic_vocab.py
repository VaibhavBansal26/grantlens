"""The made-up vocabulary shared by the synthetic corpus (seed_synthetic.py) and the load test (loadtest.py), so the
load test's queries contain words that really are in the corpus and the keyword index does real work."""
import random

SYLLABLES = ["ba", "ko", "ri", "tu", "me", "la", "no", "se", "vi", "da", "pe", "gu", "ha", "zo", "ni", "fa"]


def vocabulary(n: int = 6000, rng: random.Random | None = None) -> list[str]:
    rng = rng or random.Random(1)
    words = set()
    while len(words) < n:
        words.add("".join(rng.choice(SYLLABLES) for _ in range(rng.randint(2, 4))))
    return sorted(words)


def zipf_weights(n: int) -> list[float]:
    return [1 / (i + 1) for i in range(n)]  # a few very common words, a long tail
