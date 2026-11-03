"""Provider-neutral LLM access. Callers ask for JSON that matches a schema; only this module knows OpenAI."""
import json
import os
import threading
from typing import Protocol


class LLMError(RuntimeError):
    """The model call failed (network, quota, refusal, malformed output). Message is safe to show."""


class LLMNotConfigured(LLMError):
    pass


class LLM(Protocol):
    def complete_json(self, system: str, user: str, schema: dict, max_tokens: int = 1500) -> dict: ...


class OpenAILLM:
    def __init__(self, model: str | None = None, temperature: float | None = None):
        if not os.environ.get("OPENAI_API_KEY"):
            raise LLMNotConfigured("AI answers are not configured: set OPENAI_API_KEY on the server")
        from openai import OpenAI  # reads OPENAI_API_KEY from the environment

        self.client = OpenAI(timeout=60, max_retries=2)
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.temperature = temperature  # None = the model's default; the evaluations pass 0 to be repeatable
        self.usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}  # running totals, for cost reports
        self._usage_lock = threading.Lock()

    def complete_json(self, system: str, user: str, schema: dict, max_tokens: int = 1500) -> dict:
        import openai

        try:
            res = self.client.chat.completions.create(
                model=self.model,
                max_completion_tokens=max_tokens,
                **({"temperature": self.temperature} if self.temperature is not None else {}),
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "result", "strict": True, "schema": schema},
                },
            )
        except openai.AuthenticationError as e:
            raise LLMError("the OpenAI API key was rejected") from e
        except openai.RateLimitError as e:
            raise LLMError("the AI service is rate limited or out of quota; try again later") from e
        except openai.BadRequestError as e:
            raise LLMError(f"the AI service rejected the request: {e.message[:200]}") from e
        except openai.APIConnectionError as e:
            raise LLMError("could not reach the AI service") from e
        except openai.APIStatusError as e:
            raise LLMError(f"the AI service returned an error ({e.status_code})") from e
        if res.usage:
            with self._usage_lock:
                self.usage["calls"] += 1
                self.usage["prompt_tokens"] += res.usage.prompt_tokens
                self.usage["completion_tokens"] += res.usage.completion_tokens
        choice = res.choices[0]
        if getattr(choice.message, "refusal", None):
            raise LLMError("the model declined to answer this request")
        if choice.finish_reason == "length":
            raise LLMError("the answer was cut off; try a narrower question")
        try:
            return json.loads(choice.message.content or "")
        except json.JSONDecodeError as e:
            raise LLMError("the model returned an unreadable answer; try again") from e


def get_llm(config) -> LLM:
    if config.get("LLM_BACKEND", "openai") == "fake":
        return config["LLM_FAKE"]
    return OpenAILLM(config.get("OPENAI_MODEL"))
