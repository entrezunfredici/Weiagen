"""audit_store.py — append, query, hash chain, retention/purge, time parsing."""

import sqlite3
import threading
import time

import pytest

import audit_store


def _append(**kw):
    base = {"event": "tool_call", "tool_name": "terminal", "status": "ok"}
    base.update(kw)
    return audit_store.append_event(**base)


def test_append_and_query_newest_first():
    first = _append(tool_name="a")
    second = _append(tool_name="b")
    events = audit_store.query_events()
    assert [e["id"] for e in events] == [second, first]
    assert events[0]["args"] == {}


def test_first_row_chains_from_genesis():
    _append()
    (event,) = audit_store.query_events()
    assert event["prev_hash"] == audit_store.GENESIS_HASH
    assert event["hash"] == audit_store.compute_hash(event | {"args_json": "{}"})


def test_query_filters():
    _append(tool_name="odoo_sdk_read", platform="slack", user_id="U1", status="ok")
    _append(tool_name="odoo_sdk_delete", platform="slack", user_id="U2", status="blocked")
    _append(tool_name="terminal", platform="cli", user_id="me", status="error")

    assert {e["tool_name"] for e in audit_store.query_events(tool_name="odoo_sdk_*")} == {
        "odoo_sdk_read", "odoo_sdk_delete"
    }
    assert [e["user_id"] for e in audit_store.query_events(status="blocked")] == ["U2"]
    assert [e["tool_name"] for e in audit_store.query_events(platform="cli")] == ["terminal"]
    assert [e["tool_name"] for e in audit_store.query_events(user_id="U1")] == ["odoo_sdk_read"]


def test_prefix_filter_escapes_like_wildcards():
    _append(tool_name="odoo_x")
    _append(tool_name="odooAx")
    # "_" must be matched literally, not as LIKE's single-char wildcard.
    assert [e["tool_name"] for e in audit_store.query_events(tool_name="odoo_*")] == ["odoo_x"]


def test_since_until_filters():
    now = time.time()
    _append(ts=now - 3 * 86400, tool_name="old")
    _append(ts=now, tool_name="new")
    assert [e["tool_name"] for e in audit_store.query_events(since_ts=now - 86400)] == ["new"]
    assert [e["tool_name"] for e in audit_store.query_events(until_ts=now - 86400)] == ["old"]


def test_limit_is_clamped():
    for _ in range(3):
        _append()
    assert len(audit_store.query_events(limit=0)) == 1
    assert len(audit_store.query_events(limit=2)) == 2


def test_verify_ok_on_untouched_chain():
    for i in range(5):
        _append(tool_name=f"t{i}")
    assert audit_store.verify_chain() == {"ok": True, "checked": 5}


def test_verify_detects_edited_row(db_path):
    for i in range(3):
        _append(tool_name=f"t{i}")
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE audit_events SET status = 'ok-forged' WHERE tool_name = 't1'")
    result = audit_store.verify_chain()
    assert result["ok"] is False
    assert "edited" in result["reason"]
    assert result["checked"] == 1


def test_verify_detects_deleted_middle_row(db_path):
    ids = [_append(tool_name=f"t{i}") for i in range(3)]
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM audit_events WHERE id = ?", (ids[1],))
    result = audit_store.verify_chain()
    assert result["ok"] is False
    assert result["broken_at_id"] == ids[2]
    assert "deleted" in result["reason"]


def test_verify_detects_deleted_head_row(db_path):
    ids = [_append(tool_name=f"t{i}") for i in range(2)]
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM audit_events WHERE id = ?", (ids[0],))
    assert audit_store.verify_chain()["ok"] is False


def test_purge_moves_anchor_and_chain_stays_valid():
    now = time.time()
    _append(ts=now - 10 * 86400, tool_name="old1")
    _append(ts=now - 9 * 86400, tool_name="old2")
    _append(ts=now, tool_name="new")
    assert audit_store.purge_older_than(5) == 2
    assert [e["tool_name"] for e in audit_store.query_events()] == ["new"]
    assert audit_store.verify_chain() == {"ok": True, "checked": 1}
    # The next append keeps chaining from the surviving tail, not the anchor.
    _append(tool_name="after")
    assert audit_store.verify_chain() == {"ok": True, "checked": 2}


def test_purge_everything_then_append_chains_from_anchor():
    now = time.time()
    _append(ts=now - 10 * 86400)
    assert audit_store.purge_older_than(1) == 1
    _append()
    (event,) = audit_store.query_events()
    assert event["prev_hash"] != audit_store.GENESIS_HASH
    assert audit_store.verify_chain()["ok"] is True


def test_opportunistic_retention_purge(monkeypatch):
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "30")
    now = time.time()
    _append(ts=now - 40 * 86400, tool_name="expired")
    # The write above runs the first daily purge relative to its own ts, so
    # it survives it; the next write (more than a day later) purges it.
    _append(ts=now, tool_name="fresh")
    assert [e["tool_name"] for e in audit_store.query_events()] == ["fresh"]
    assert audit_store.verify_chain()["ok"] is True


def test_retention_zero_keeps_everything(monkeypatch):
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "0")
    now = time.time()
    _append(ts=now - 4000 * 86400)
    _append(ts=now)
    assert len(audit_store.query_events()) == 2


@pytest.mark.parametrize("raw, expected", [("", 90), ("abc", 90), ("-5", 0), ("7", 7)])
def test_retention_days_parsing(monkeypatch, raw, expected):
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", raw)
    assert audit_store.retention_days() == expected


def test_concurrent_appends_keep_a_valid_chain():
    def worker(n):
        for i in range(20):
            _append(tool_name=f"w{n}-{i}")

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert audit_store.verify_chain() == {"ok": True, "checked": 100}


def test_stats():
    _append(tool_name="a", status="ok")
    _append(tool_name="a", status="blocked")
    _append(tool_name="b", status="ok")
    s = audit_store.stats()
    assert s["total"] == 3
    assert s["by_status"] == {"ok": 2, "blocked": 1}
    assert s["top_tools"][0] == {"tool_name": "a", "count": 2}
    assert s["oldest_ts"] is not None


@pytest.mark.parametrize(
    "value, delta",
    [("30m", 1800), ("24h", 86400), ("7d", 7 * 86400), ("2w", 14 * 86400), (" 5 H ", 5 * 3600)],
)
def test_parse_since_relative(value, delta):
    assert audit_store.parse_since(value, now=1_000_000.0) == 1_000_000.0 - delta


def test_parse_since_iso_and_empty():
    assert audit_store.parse_since("1970-01-02") == 86400.0
    assert audit_store.parse_since("") is None
    assert audit_store.parse_since(None) is None


def test_parse_since_invalid():
    with pytest.raises(ValueError, match="invalid time filter"):
        audit_store.parse_since("yesterday")
