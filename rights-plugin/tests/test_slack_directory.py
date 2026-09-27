"""slack_directory.fetch_slack_members — Slack Web API client, no real network.

`_urlopen` is monkeypatched to a fake so these tests never touch a socket —
see slack_directory.py's docstring for why that indirection exists.
"""

import json

import pytest

import slack_directory
from rights_w_main.errors_manager.errors import ServiceError


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(pages):
    """Returns a function that pops one page per call, ignoring the request."""
    calls = []

    def _opener(request, timeout=None):  # noqa: ARG001
        calls.append(request.full_url)
        return _FakeResponse(pages.pop(0))

    _opener.calls = calls
    return _opener


def test_fetch_slack_members_single_page(monkeypatch):
    monkeypatch.setattr(slack_directory, "_urlopen", _fake_urlopen([
        {
            "ok": True,
            "members": [
                {"id": "U1", "profile": {"display_name": "Fred", "real_name": "Fred M.", "email": "fred@x.com"}},
                {"id": "U2", "profile": {"real_name": "Ana"}},
            ],
        },
    ]))
    members = slack_directory.fetch_slack_members("xoxb-fake")
    assert {m["external_user_id"] for m in members} == {"U1", "U2"}
    fred = next(m for m in members if m["external_user_id"] == "U1")
    assert fred["display_name"] == "Fred"
    assert fred["email"] == "fred@x.com"
    ana = next(m for m in members if m["external_user_id"] == "U2")
    assert ana["display_name"] == "Ana"  # falls back to real_name when display_name is blank


def test_fetch_slack_members_filters_bots_and_deleted(monkeypatch):
    monkeypatch.setattr(slack_directory, "_urlopen", _fake_urlopen([
        {
            "ok": True,
            "members": [
                {"id": "U1", "profile": {"display_name": "Fred"}},
                {"id": "B1", "is_bot": True, "profile": {"display_name": "A Bot"}},
                {"id": "U2", "deleted": True, "profile": {"display_name": "Gone"}},
                {"id": "USLACKBOT", "profile": {"display_name": "Slackbot"}},
            ],
        },
    ]))
    members = slack_directory.fetch_slack_members("xoxb-fake")
    assert {m["external_user_id"] for m in members} == {"U1"}


def test_fetch_slack_members_paginates_via_cursor(monkeypatch):
    opener = _fake_urlopen([
        {"ok": True, "members": [{"id": "U1", "profile": {"display_name": "Fred"}}],
         "response_metadata": {"next_cursor": "page2"}},
        {"ok": True, "members": [{"id": "U2", "profile": {"display_name": "Ana"}}],
         "response_metadata": {"next_cursor": ""}},
    ])
    monkeypatch.setattr(slack_directory, "_urlopen", opener)
    members = slack_directory.fetch_slack_members("xoxb-fake")
    assert {m["external_user_id"] for m in members} == {"U1", "U2"}
    assert len(opener.calls) == 2
    assert "cursor=page2" in opener.calls[1]


def test_fetch_slack_members_raises_service_error_on_slack_error(monkeypatch):
    monkeypatch.setattr(slack_directory, "_urlopen", _fake_urlopen([
        {"ok": False, "error": "invalid_auth"},
    ]))
    with pytest.raises(ServiceError):
        slack_directory.fetch_slack_members("bad-token")


def test_fetch_slack_members_raises_service_error_on_network_failure(monkeypatch):
    import urllib.error

    def _opener(request, timeout=None):  # noqa: ARG001
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(slack_directory, "_urlopen", _opener)
    with pytest.raises(ServiceError):
        slack_directory.fetch_slack_members("xoxb-fake")
