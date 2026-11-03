"""Provider-neutral LLM access. Callers ask for JSON that matches a schema; only this module knows the provider.

Two providers speak the same chat API: OpenAI (which can force output to match a schema) and Hugging Face's
Inference Providers router (Llama and other open models), which mostly cannot. For those, the schema goes into
the prompt, the reply is validated against it here, and an invalid reply gets one retry with the error shown.
"""
import json
import os
import re
import threading
from typing import Protocol

import jsonschema


class LLMError(RuntimeError):
    """The model call failed (network, quota, refusal, malformed output). Message is safe to show."""


class LLMNotConfigured(LLMError):
    pass


class LLM(Protocol):
    def complete_json(self, system: str, user: str, schema: dict, max_tokens: int = 1500) -> dict: ...


HF_BASE_URL = "https://router.huggingface.co/v1"
FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


class OpenAILLM:
    """Any OpenAI-compatible chat endpoint. Defaults are OpenAI itself."""

    def __init__(self, model: str | None = None, temperature: float | None = None, *, base_url: str | None = None,
                 key_env: str = "OPENAI_API_KEY", model_env: str = "OPENAI_MODEL", default_model: str = "gpt-4o-mini",
                 structured: str = "json_schema", token_param: str = "max_completion_tokens", service: str = "OpenAI"):
        if not os.environ.get(key_env):
            raise LLMNotConfigured(f"AI answers are not configured: set {key_env} on the server")
        from openai import OpenAI

        self.client = OpenAI(api_key=os.environ[key_env], base_url=base_url, timeout=60, max_retries=2)
        self.model = model or os.environ.get(model_env, default_model)
        self.temperature = temperature  # None = the model's default; the evaluations pass 0 to be repeatable
        self.structured, self.token_param, self.service = structured, token_param, service
        self.usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}  # running totals, for cost reports
        self.served: set[str] = set()  # model names providers actually answered with (may be a variant)
        self._usage_lock = threading.Lock()

    def _chat(self, messages: list[dict], schema: dict, max_tokens: int):
        import openai

        if self.structured == "json_schema":
            fmt = {"type": "json_schema", "json_schema": {"name": "result", "strict": True, "schema": schema}}
        else:
            fmt = {"type": "json_object"}
        try:
            res = self.client.chat.completions.create(
                model=self.model, messages=messages, response_format=fmt, **{self.token_param: max_tokens},
                **({"temperature": self.temperature} if self.temperature is not None else {}),
            )
        except openai.AuthenticationError as e:
            raise LLMError(f"the {self.service} API key was rejected") from e
        except openai.RateLimitError as e:
            raise LLMError("the AI service is rate limited or out of quota; try again later") from e
        except openai.BadRequestError as e:
            raise LLMError(f"the AI service rejected the request: {e.message[:200]}") from e
        except openai.APIConnectionError as e:
            raise LLMError("could not reach the AI service") from e
        except openai.APIStatusError as e:
            raise LLMError(f"the AI service returned an error ({e.status_code})") from e
        if getattr(res, "model", None):
            self.served.add(res.model)
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
        return choice.message.content or ""

    @staticmethod
    def _parse(text: str):
        match = FENCE.match(text)
        return json.loads(match.group(1) if match else text)

    def complete_json(self, system: str, user: str, schema: dict, max_tokens: int = 1500) -> dict:
        if self.structured == "json_schema":  # the provider guarantees the shape
            messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
            try:
                return self._parse(self._chat(messages, schema, max_tokens))
            except json.JSONDecodeError as e:
                raise LLMError("the model returned an unreadable answer; try again") from e
        # No schema enforcement on the provider's side: state the schema, check the reply ourselves, retry once.
        system += ("\n\nReply with ONLY a JSON object that matches this JSON Schema. No prose, no code fences.\n"
                   f"Schema: {json.dumps(schema)}")
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        problem = ""
        for _ in range(2):
            text = self._chat(messages, schema, max_tokens)
            try:
                value = self._parse(text)
                jsonschema.validate(value, schema)
                return value
            except (json.JSONDecodeError, jsonschema.ValidationError) as e:
                problem = getattr(e, "message", None) or str(e)
                messages = messages[:2] + [{"role": "assistant", "content": text[:2000]},
                                           {"role": "user", "content": f"That reply was not valid ({problem[:200]}). "
                                                                       "Reply again with ONLY the corrected JSON object."}]
        raise LLMError("the model returned an unreadable answer; try again")


def huggingface_llm(model: str | None = None, temperature: float | None = None) -> OpenAILLM:
    """Llama and other open models through Hugging Face Inference Providers (set HF_TOKEN; HF_MODEL picks the model)."""
    return OpenAILLM(model, temperature, base_url=HF_BASE_URL, key_env="HF_TOKEN", model_env="HF_MODEL",
                     default_model="meta-llama/Llama-3.1-8B-Instruct", structured="json_object",
                     token_param="max_tokens", service="Hugging Face")


def get_llm(config) -> LLM:
    backend = config.get("LLM_BACKEND", "openai")
    if backend == "fake":
        return config["LLM_FAKE"]
    if backend == "hf":
        return huggingface_llm(config.get("HF_MODEL"))
    return OpenAILLM(config.get("OPENAI_MODEL"))
