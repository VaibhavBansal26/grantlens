"""Shared helpers for the AI quality evaluations.

Run from apps/api, with the dev database up:   uv run python -m evals.run_all
The evaluations call the real model with the key from the repo's .env and cost a few cents (it prints the total).
"""
import math
import os
import re
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def load_openai_key() -> None:
    """Read only OPENAI_API_KEY, OPENAI_MODEL and OPENALEX_API_KEY from .env into this process. The rest of that file points
    at Docker-internal hosts, so it is deliberately not loaded; the key is never printed."""
    for line in ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []:
        m = re.match(r"^\s*(OPENAI_API_KEY|OPENAI_MODEL|OPENALEX_API_KEY)\s*=\s*([^#\s]*)", line)
        if m and m.group(2):
            os.environ.setdefault(m.group(1), m.group(2))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion: honest about how little a small sample proves."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def rate(k: int, n: int) -> str:
    if n == 0:
        return "n/a (0 cases)"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {100 * k / n:.0f}% (95% CI {100 * lo:.0f} to {100 * hi:.0f}%)"


def row(label: str, k: int, n: int) -> str:
    """One markdown table row: a label and a rate with its confidence interval."""
    return f"| {label} | {rate(k, n)} |"


def load_hf_token() -> None:
    """For the evaluations only: use the saved Hugging Face login if HF_TOKEN is not set. The server itself
    requires HF_TOKEN in its environment."""
    token_file = Path.home() / ".cache" / "huggingface" / "token"
    if not os.environ.get("HF_TOKEN") and token_file.exists():
        os.environ["HF_TOKEN"] = token_file.read_text().strip()


def make_llm(backend: str = "openai"):
    from grantlens_api.llm import OpenAILLM, huggingface_llm

    load_openai_key()
    if backend == "hf":
        load_hf_token()
        return huggingface_llm(temperature=0)
    return OpenAILLM(temperature=0)


def make_app():
    from grantlens_api import create_app

    return create_app()


def cost_estimate(usage: dict, model: str) -> str:
    # USD per million tokens (input, output). gpt-4o-mini's list price; others are unknown here, so say so.
    prices = {"gpt-4o-mini": (0.15, 0.60)}
    if model.startswith("meta-llama/") and usage["calls"]:
        return f"{usage['calls']} calls, {usage['prompt_tokens']:,} prompt + {usage['completion_tokens']:,} completion tokens (billed by the provider, a few cents at most)"
    p = prices.get(model)
    tokens = f"{usage['calls']} calls, {usage['prompt_tokens']:,} prompt + {usage['completion_tokens']:,} completion tokens"
    if not p:
        return f"{tokens} (no price on file for {model})"
    usd = usage["prompt_tokens"] * p[0] / 1e6 + usage["completion_tokens"] * p[1] / 1e6
    return f"{tokens}, about ${usd:.3f}"
