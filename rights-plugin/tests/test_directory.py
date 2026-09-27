"""directory.py — sync orchestration (sync_now / ensure_fresh / list_cached).

SLACK_BOT_TOKEN is unset by conftest.py's autouse fixture unless a test sets
it itself — real network calls are never reachable from here anyway since
directory.sync_now() delegates to slack_directory.fetch_slack_members(),
which is monkeypatched at the module level (see below), not called for
real.
"""

import time

import pytest

import directory
import models
import slack_directory
from rights_w_main.errors_manager.errors import ConfigurationError, ServiceError


def _fake_members(*ids):
    return [{"external_user_id": i, "display_name": i} for i in ids]


# ---------------------------------------------------------------------------
# sync_now
# ---------------------------------------------------------------------------


def test_sync_now_raises_when_token_missing():
    with pytest.raises(ConfigurationError):
        directory.sync_now("slack")


def test_sync_now_raises_for_unknown_platform(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    with pytest.raises(ConfigurationError):
        directory.sync_now("carrier-pigeon")


def test_sync_now_stores_fetched_members(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    monkeypatch.setattr(slack_directory, "fetch_slack_members", lambda token: _fake_members("U1", "U2"))
    result = directory.sync_now("slack")
    assert {e["external_user_id"] for e in result} == {"U1", "U2"}
    assert {e.external_user_id for e in models.list_directory_entries("slack")} == {"U1", "U2"}


def test_sync_now_propagates_slack_service_error(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")

    def _raise(token):
        raise ServiceError("Slack users.list failed: invalid_auth")

    monkeypatch.setattr(slack_directory, "fetch_slack_members", _raise)
    with pytest.raises(ServiceError):
        directory.sync_now("slack")


# ---------------------------------------------------------------------------
# ensure_fresh
# ---------------------------------------------------------------------------


def test_ensure_fresh_syncs_when_never_synced(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    monkeypatch.setattr(slack_directory, "fetch_slack_members", lambda token: _fake_members("U1"))
    directory.ensure_fresh("slack")
    assert {e.external_user_id for e in models.list_directory_entries("slack")} == {"U1"}


def test_ensure_fresh_skips_when_fresh(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    calls = []
    monkeypatch.setattr(slack_directory, "fetch_slack_members", lambda token: calls.append(1) or _fake_members("U1"))
    directory.ensure_fresh("slack")  # first call: stale (never synced) -> syncs
    assert len(calls) == 1
    directory.ensure_fresh("slack")  # second call: fresh -> no-op
    assert len(calls) == 1


def test_ensure_fresh_resyncs_once_past_ttl(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    monkeypatch.setattr(slack_directory, "fetch_slack_members", lambda token: _fake_members("U1"))
    directory.ensure_fresh("slack", max_age_seconds=0)
    time.sleep(0.01)
    calls = []
    monkeypatch.setattr(slack_directory, "fetch_slack_members", lambda token: calls.append(1) or _fake_members("U2"))
    directory.ensure_fresh("slack", max_age_seconds=0)
    assert len(calls) == 1  # TTL of 0 means "always stale" -> always resyncs


def test_ensure_fresh_never_raises_when_token_missing():
    directory.ensure_fresh("slack")  # no SLACK_BOT_TOKEN set (conftest pops it) -> must not raise
    assert models.list_directory_entries("slack") == []


def test_ensure_fresh_never_raises_when_slack_call_fails(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")

    def _raise(token):
        raise ServiceError("boom")

    monkeypatch.setattr(slack_directory, "fetch_slack_members", _raise)
    directory.ensure_fresh("slack")  # must swallow, not raise
    assert models.list_directory_entries("slack") == []


def test_ensure_fresh_is_a_noop_for_unknown_platform():
    directory.ensure_fresh("carrier-pigeon")  # no sync func registered -> silently does nothing
    assert models.list_directory_entries("carrier-pigeon") == []


# ---------------------------------------------------------------------------
# list_cached
# ---------------------------------------------------------------------------


def test_list_cached_never_triggers_a_sync(monkeypatch):
    calls = []
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    monkeypatch.setattr(slack_directory, "fetch_slack_members", lambda token: calls.append(1) or _fake_members("U1"))
    assert directory.list_cached("slack") == []
    assert calls == []


def test_list_cached_reflects_last_sync(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    monkeypatch.setattr(slack_directory, "fetch_slack_members", lambda token: _fake_members("U1", "U2"))
    directory.sync_now("slack")
    cached = directory.list_cached("slack")
    assert {e["external_user_id"] for e in cached} == {"U1", "U2"}
