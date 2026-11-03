"""The OpenAI wrapper, run through the real SDK against a local stand-in server (no key, no network)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from grantlens_api.llm import LLMError, LLMNotConfigured, OpenAILLM

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"],
          "additionalProperties": False}


def completion(content, finish="stop", refusal=None):
    return {
        "id": "chatcmpl-1", "object": "chat.completion", "created": 0, "model": "test-model",
        "choices": [{"index": 0, "finish_reason": finish,
                     "message": {"role": "assistant", "content": content, "refusal": refusal}}],
    }


@pytest.fixture
def server(monkeypatch):
    state = {"requests": [], "status": 200, "body": completion('{"answer": "ok"}'), "queue": []}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            state["requests"].append((self.path, self.headers.get("Authorization"), json.loads(self.rfile.read(length))))
            payload = json.dumps(state["queue"].pop(0) if state["queue"] else state["body"]).encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{httpd.server_port}/v1")
    yield state
    httpd.shutdown()


def test_request_shape_and_parsing(server):
    out = OpenAILLM("test-model").complete_json("SYS", "USER", SCHEMA, max_tokens=321)
    assert out == {"answer": "ok"}
    path, auth, body = server["requests"][0]
    assert path == "/v1/chat/completions" and auth == "Bearer test-key-not-real"
    assert body["model"] == "test-model" and body["max_completion_tokens"] == 321
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"] == SCHEMA


def test_temperature_is_sent_only_when_asked_and_usage_is_counted(server):
    server["body"]["usage"] = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}
    default = OpenAILLM("m")
    default.complete_json("s", "u", SCHEMA)
    assert "temperature" not in server["requests"][-1][2]  # production behaviour is unchanged
    pinned = OpenAILLM("m", temperature=0)
    pinned.complete_json("s", "u", SCHEMA)
    pinned.complete_json("s", "u", SCHEMA)
    assert server["requests"][-1][2]["temperature"] == 0
    assert pinned.usage == {"calls": 2, "prompt_tokens": 240, "completion_tokens": 60}


def test_model_comes_from_env_when_not_given(server, monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "env-model")
    OpenAILLM().complete_json("s", "u", SCHEMA)
    assert server["requests"][0][2]["model"] == "env-model"


@pytest.mark.parametrize(("status", "body", "message"), [
    (401, {"error": {"message": "bad key"}}, "key was rejected"),
    (429, {"error": {"message": "slow down"}}, "rate limited"),
    (400, {"error": {"message": "unsupported parameter"}}, "rejected the request"),
])
def test_http_errors_become_safe_messages(server, status, body, message):
    server["status"], server["body"] = status, body
    with pytest.raises(LLMError, match=message) as e:
        OpenAILLM("m").complete_json("s", "u", SCHEMA)
    assert "test-key-not-real" not in str(e.value)  # the key never leaks into a message


def test_refusal_truncation_and_garbage_are_errors(server):
    server["body"] = completion(None, refusal="I can't help with that")
    with pytest.raises(LLMError, match="declined"):
        OpenAILLM("m").complete_json("s", "u", SCHEMA)
    server["body"] = completion('{"answer": "cut', finish="length")
    with pytest.raises(LLMError, match="cut off"):
        OpenAILLM("m").complete_json("s", "u", SCHEMA)
    server["body"] = completion("not json at all")
    with pytest.raises(LLMError, match="unreadable"):
        OpenAILLM("m").complete_json("s", "u", SCHEMA)


def test_missing_key_is_reported_before_any_request(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMNotConfigured, match="OPENAI_API_KEY"):
        OpenAILLM("m")


# ---- providers that cannot force a schema (Llama through Hugging Face): prompt + validate + retry once ------

def compat(server_url_env="OPENAI_BASE_URL"):
    import os

    return OpenAILLM("llama-test", base_url=os.environ[server_url_env], structured="json_object",
                     token_param="max_tokens", service="Hugging Face")


def test_json_object_mode_puts_the_schema_in_the_prompt_and_uses_max_tokens(server):
    out = compat().complete_json("SYS", "USER", SCHEMA, max_tokens=77)
    assert out == {"answer": "ok"}
    body = server["requests"][0][2]
    assert body["response_format"] == {"type": "json_object"} and body["max_tokens"] == 77
    assert "max_completion_tokens" not in body
    system = body["messages"][0]["content"]
    assert system.startswith("SYS") and "JSON Schema" in system and '"answer"' in system  # the schema is stated in words


def test_fenced_json_is_accepted(server):
    server["body"] = completion('```json\n{"answer": "fenced"}\n```')
    assert compat().complete_json("s", "u", SCHEMA) == {"answer": "fenced"}


def test_an_invalid_reply_is_retried_once_with_the_error_shown(server):
    server["body"]["usage"] = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    server["queue"] = [completion('{"wrong_key": 1}'), completion('{"answer": "fixed"}')]
    llm = compat()
    assert llm.complete_json("s", "u", SCHEMA) == {"answer": "fixed"}
    retry = server["requests"][1][2]["messages"]
    assert [m["role"] for m in retry] == ["system", "user", "assistant", "user"]
    assert "not valid" in retry[-1]["content"] and retry[2]["content"] == '{"wrong_key": 1}'  # it sees its own mistake


def test_two_invalid_replies_give_up_without_looping(server):
    server["queue"] = [completion("not json at all"), completion('{"answer": 5}')]  # wrong type the second time
    with pytest.raises(LLMError, match="unreadable"):
        compat().complete_json("s", "u", SCHEMA)
    assert len(server["requests"]) == 2  # exactly one retry, never more


def test_strict_provider_mode_never_retries(server):
    server["body"] = completion("not json")
    with pytest.raises(LLMError, match="unreadable"):
        OpenAILLM("m").complete_json("s", "u", SCHEMA)
    assert len(server["requests"]) == 1


def test_hugging_face_backend_is_selected_by_config_and_needs_its_own_key(monkeypatch):
    from grantlens_api.llm import HF_BASE_URL, get_llm

    monkeypatch.delenv("HF_TOKEN", raising=False)
    with pytest.raises(LLMNotConfigured, match="HF_TOKEN"):
        get_llm({"LLM_BACKEND": "hf"})
    monkeypatch.setenv("HF_TOKEN", "hf_test_not_real")
    llm = get_llm({"LLM_BACKEND": "hf", "HF_MODEL": "meta-llama/Llama-3.1-8B-Instruct"})
    assert llm.structured == "json_object" and llm.token_param == "max_tokens" and llm.model == "meta-llama/Llama-3.1-8B-Instruct"
    assert str(llm.client.base_url).startswith(HF_BASE_URL)


def test_service_name_appears_in_key_errors(server):
    server["status"], server["body"] = 401, {"error": {"message": "bad key"}}
    with pytest.raises(LLMError, match="Hugging Face API key was rejected") as e:
        compat().complete_json("s", "u", SCHEMA)
    assert "test-key-not-real" not in str(e.value)
