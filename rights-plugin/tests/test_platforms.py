"""platforms.py — which messaging platforms look configured, by env var presence."""

import platforms


def test_all_platforms_includes_every_known_platform():
    slugs = {p["slug"] for p in platforms.all_platforms()}
    assert "slack" in slugs
    assert "telegram" in slugs
    assert len(slugs) == len(platforms._KNOWN_PLATFORMS)


def test_slack_reports_configured_when_token_env_var_is_set(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    slack = next(p for p in platforms.all_platforms() if p["slug"] == "slack")
    assert slack["configured"] is True


def test_slack_reports_not_configured_when_token_env_var_is_absent(monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    slack = next(p for p in platforms.all_platforms() if p["slug"] == "slack")
    assert slack["configured"] is False


def test_connected_platforms_only_returns_configured_ones(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    connected = platforms.connected_platforms()
    slugs = {p["slug"] for p in connected}
    assert "slack" in slugs
    assert "telegram" not in slugs
    assert all(p["configured"] for p in connected)


def test_connected_platforms_empty_when_nothing_configured(monkeypatch):
    for _label, token_var, _slug in platforms._KNOWN_PLATFORMS:
        monkeypatch.delenv(token_var, raising=False)
    assert platforms.connected_platforms() == []
