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
    state = {"requests": [], "status": 200, "body": completion('{"answer": "ok"}')}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            state["requests"].append((self.path, self.headers.get("Authorization"), json.loads(self.rfile.read(length))))
            payload = json.dumps(state["body"]).encode()
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
