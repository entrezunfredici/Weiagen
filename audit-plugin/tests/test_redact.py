"""audit_redact.py — key-based redaction, truncation, size cap."""

import json

import pytest

import audit_redact
from audit_redact import REDACTED, redact_args_json, redact_message, redact_value


@pytest.mark.parametrize(
    "key",
    ["password", "db_password", "passwd", "secret", "client_secret", "token", "caller_token",
     "access_token", "api_key", "apiKey", "API-KEY", "Authorization", "auth", "x-auth-token",
     "credentials", "private_key", "cookie", "session_key", "signature"],
)
def test_sensitive_keys(key):
    assert audit_redact.is_sensitive_key(key)


@pytest.mark.parametrize("key", ["author_id", "name", "model", "command", "path", "domain", "fields"])
def test_non_sensitive_keys(key):
    assert not audit_redact.is_sensitive_key(key)


def test_nested_redaction():
    value = {
        "model": "res.partner",
        "values": {"name": "ACME", "password": "hunter2"},
        "headers": [{"Authorization": "Bearer abc"}, {"x": 1}],
        "caller_token": "eyJ...signed",
    }
    out = redact_value(value)
    assert out["model"] == "res.partner"
    assert out["values"] == {"name": "ACME", "password": REDACTED}
    assert out["headers"] == [{"Authorization": REDACTED}, {"x": 1}]
    assert out["caller_token"] == REDACTED


def test_long_strings_are_truncated():
    out = redact_value({"content": "x" * 2000})
    assert out["content"].startswith("x" * audit_redact.MAX_STRING_CHARS)
    assert out["content"].endswith("[+1500 chars]")


def test_depth_is_bounded():
    deep = current = {}
    for _ in range(20):
        current["n"] = {}
        current = current["n"]
    encoded = json.dumps(redact_value(deep), ensure_ascii=False)
    assert "[…]" in encoded


def test_non_json_values_are_stringified():
    assert redact_value({"obj": object()})["obj"].startswith("<object object")


def test_args_json_accepts_json_string_and_raw_string():
    assert json.loads(redact_args_json('{"token": "t", "a": 1}')) == {"token": REDACTED, "a": 1}
    assert json.loads(redact_args_json("not json")) == {"_raw": "not json"}
    assert redact_args_json(None) == "{}"


def test_args_json_total_size_cap():
    big = {f"k{i}": "y" * 400 for i in range(50)}
    encoded = redact_args_json(big)
    parsed = json.loads(encoded)
    assert parsed["_truncated"] is True
    assert len(parsed["_preview"]) == audit_redact.MAX_ARGS_JSON_CHARS


def test_content_redactor_is_applied_when_available(monkeypatch):
    monkeypatch.setattr(audit_redact, "_hermes_redact", lambda text, force: text.replace("sk-live-123", "***"))
    out = redact_value({"command": "curl -H 'X: sk-live-123' https://api"})
    assert out["command"] == "curl -H 'X: ***' https://api"


def test_content_redactor_failure_does_not_break(monkeypatch):
    def boom(text, force):
        raise RuntimeError("nope")

    monkeypatch.setattr(audit_redact, "_hermes_redact", boom)
    assert redact_value({"command": "ls"}) == {"command": "ls"}


def test_redact_message():
    assert redact_message(None) == ""
    assert redact_message("x" * 600).endswith("[+100 chars]")
