"""Append-only, hash-chained audit log stored in SQLite.

Why SQLite and not the JSON flat-files ``odoo-plugin``/``rights-plugin``
use (see ``.agents/DECISIONS.md``, 2026-09-24): this table is written on
*every* tool call, from several threads (Hermes can run tool calls
concurrently) and read from another process (the dashboard). A JSON
flat-file would be rewritten in full on every event (O(n) per write) and
race between writers. SQLite is stdlib, handles cross-process locking
itself, and WAL mode lets the dashboard read while the gateway writes.

Tamper *evidence*, not tamper *proofing*: every row stores
``hash = sha256(prev_hash + canonical_json(row))``. Editing or deleting a
row in the middle breaks the chain, which ``verify_chain()`` reports. A
process with write access to the file can still rewrite the whole chain
from the tampered row onward — protecting against that needs the log to
live outside the audited process's reach (the "microservice" option, see
``.agents/DECISIONS.md``). Deleting rows from the head is covered by the
purge anchor (``meta.anchor_hash``); truncating the tail is not detectable
from the file alone.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

GENESIS_HASH = "0" * 64

# Columns covered by the hash, in a fixed order. `id` and `hash` are
# excluded (id is assigned by SQLite, hash is the output).
_HASHED_COLUMNS = (
    "ts", "event", "tool_name", "status", "error_type", "error_message",
    "duration_ms", "session_id", "task_id", "tool_call_id", "turn_id",
    "platform", "user_id", "args_json", "result_size", "prev_hash",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL    NOT NULL,
    event         TEXT    NOT NULL,
    tool_name     TEXT    NOT NULL DEFAULT '',
    status        TEXT    NOT NULL DEFAULT '',
    error_type    TEXT    NOT NULL DEFAULT '',
    error_message TEXT    NOT NULL DEFAULT '',
    duration_ms   INTEGER NOT NULL DEFAULT 0,
    session_id    TEXT    NOT NULL DEFAULT '',
    task_id       TEXT    NOT NULL DEFAULT '',
    tool_call_id  TEXT    NOT NULL DEFAULT '',
    turn_id       TEXT    NOT NULL DEFAULT '',
    platform      TEXT    NOT NULL DEFAULT '',
    user_id       TEXT    NOT NULL DEFAULT '',
    args_json     TEXT    NOT NULL DEFAULT '{}',
    result_size   INTEGER NOT NULL DEFAULT 0,
    prev_hash     TEXT    NOT NULL,
    hash          TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events (ts);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_events (platform, user_id);
CREATE INDEX IF NOT EXISTS idx_audit_tool ON audit_events (tool_name);
CREATE TABLE IF NOT EXISTS audit_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_DEFAULT_RETENTION_DAYS = 90
_PURGE_INTERVAL_SECONDS = 24 * 3600


_DURATION = re.compile(r"^\s*(\d+)\s*([smhdw])\s*$", re.IGNORECASE)
_DURATION_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 7 * 86400}


def parse_since(value: str | None, *, now: float | None = None) -> float | None:
    """Parse ``"30m"``/``"24h"``/``"7d"``/``"2w"`` or an ISO date/datetime into an epoch timestamp.

    Returns ``None`` for an empty value. Raises ``ValueError`` on anything
    else, so callers can report a clear message instead of silently
    ignoring the filter.
    """
    if value is None or not str(value).strip():
        return None
    match = _DURATION.match(str(value))
    if match:
        amount, unit = int(match.group(1)), match.group(2).lower()
        return (now if now is not None else time.time()) - amount * _DURATION_SECONDS[unit]
    try:
        parsed = datetime.fromisoformat(str(value).strip())
    except ValueError:
        raise ValueError(
            f"invalid time filter {value!r}: use e.g. '30m', '24h', '7d', '2w' or an ISO date '2026-09-24'"
        ) from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _db_path() -> Path:
    return Path(os.environ["AUDIT_DB_PATH"])


def retention_days() -> int:
    """Return the configured retention in days (``AUDIT_RETENTION_DAYS``, 0 = keep forever)."""
    raw = os.environ.get("AUDIT_RETENTION_DAYS", "").strip()
    if not raw:
        return _DEFAULT_RETENTION_DAYS
    try:
        return max(0, int(raw))
    except ValueError:
        return _DEFAULT_RETENTION_DAYS


def compute_hash(row: dict[str, Any]) -> str:
    """Return the chain hash of *row* (a dict holding every ``_HASHED_COLUMNS`` key)."""
    canonical = json.dumps(
        [row[c] for c in _HASHED_COLUMNS], ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256((row["prev_hash"] + canonical).encode("utf-8")).hexdigest()


# One lock per process: serializes writers from concurrent tool-call
# threads before they even reach SQLite. Cross-process writers (CLI purge
# vs gateway) are serialized by `BEGIN IMMEDIATE` below.
_write_lock = threading.Lock()
_initialized_paths: set[str] = set()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0, isolation_level=None)
    try:
        conn.row_factory = sqlite3.Row
        if str(path) not in _initialized_paths:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)
            _initialized_paths.add(str(path))
        yield conn
    finally:
        conn.close()


def _get_meta(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM audit_meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO audit_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def append_event(**fields: Any) -> int:
    """Append one event to the chain and return its row id.

    Unknown keys are ignored; missing ones default to empty/zero. ``ts``
    defaults to now. Also runs the retention purge at most once per day
    (opportunistic, no background job — Hermes's plugin API has none).
    """
    row: dict[str, Any] = {c: "" for c in _HASHED_COLUMNS}
    row.update({"duration_ms": 0, "result_size": 0, "args_json": "{}"})
    row.update({k: v for k, v in fields.items() if k in _HASHED_COLUMNS and v is not None})
    row["ts"] = float(fields.get("ts") or time.time())
    row["duration_ms"] = int(row["duration_ms"] or 0)
    row["result_size"] = int(row["result_size"] or 0)
    for c in _HASHED_COLUMNS:
        if c not in ("ts", "duration_ms", "result_size"):
            row[c] = str(row[c])

    with _write_lock, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            last = conn.execute("SELECT hash FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()
            row["prev_hash"] = last["hash"] if last else _get_meta(conn, "anchor_hash", GENESIS_HASH)
            row["hash"] = compute_hash(row)
            cols = list(_HASHED_COLUMNS) + ["hash"]
            cur = conn.execute(
                f"INSERT INTO audit_events ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                [row[c] for c in cols],
            )
            new_id = int(cur.lastrowid)
            _maybe_purge(conn, now=row["ts"])
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return new_id


def _maybe_purge(conn: sqlite3.Connection, *, now: float) -> None:
    days = retention_days()
    if days <= 0:
        return
    last_purge = float(_get_meta(conn, "last_purge_ts", "0") or 0)
    if now - last_purge < _PURGE_INTERVAL_SECONDS:
        return
    _purge_before(conn, now - days * 86400)
    _set_meta(conn, "last_purge_ts", str(now))


def _purge_before(conn: sqlite3.Connection, cutoff_ts: float) -> int:
    """Delete rows older than *cutoff_ts*, moving the chain anchor forward.

    Rows are deleted by id (a contiguous head of the chain), never by ts
    alone: a row with an out-of-order clock must not punch a hole in the
    middle of the chain.
    """
    last_old = conn.execute(
        "SELECT id, hash FROM audit_events WHERE id <= "
        "(SELECT COALESCE(MAX(id), 0) FROM audit_events WHERE ts < ?) ORDER BY id DESC LIMIT 1",
        (cutoff_ts,),
    ).fetchone()
    if last_old is None:
        return 0
    deleted = conn.execute("DELETE FROM audit_events WHERE id <= ?", (last_old["id"],)).rowcount
    _set_meta(conn, "anchor_hash", last_old["hash"])
    return int(deleted)


def purge_older_than(days: int) -> int:
    """Delete every event older than *days* days. Returns the number of rows deleted."""
    with _write_lock, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            deleted = _purge_before(conn, time.time() - days * 86400)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return deleted


def query_events(
    *,
    platform: str | None = None,
    user_id: str | None = None,
    tool_name: str | None = None,
    status: str | None = None,
    event: str | None = None,
    since_ts: float | None = None,
    until_ts: float | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return matching events, newest first. ``tool_name`` accepts a ``*`` suffix wildcard."""
    clauses: list[str] = []
    params: list[Any] = []
    for column, value in (("platform", platform), ("user_id", user_id), ("status", status), ("event", event)):
        if value:
            clauses.append(f"{column} = ?")
            params.append(value)
    if tool_name:
        if tool_name.endswith("*"):
            clauses.append("tool_name LIKE ? ESCAPE '\\'")
            prefix = tool_name[:-1].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(prefix + "%")
        else:
            clauses.append("tool_name = ?")
            params.append(tool_name)
    if since_ts is not None:
        clauses.append("ts >= ?")
        params.append(since_ts)
    if until_ts is not None:
        clauses.append("ts < ?")
        params.append(until_ts)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit = max(1, min(int(limit), 1000))
    params.extend([limit, max(0, int(offset))])
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM audit_events {where} ORDER BY id DESC LIMIT ? OFFSET ?", params
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    out = dict(row)
    try:
        out["args"] = json.loads(out.pop("args_json"))
    except (ValueError, TypeError):
        out["args"] = {}
    return out


def stats(*, since_ts: float | None = None) -> dict[str, Any]:
    """Return event counts grouped by status and the ten most called tools."""
    where, params = ("WHERE ts >= ?", [since_ts]) if since_ts is not None else ("", [])
    with _connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS n FROM audit_events {where}", params).fetchone()["n"]
        by_status = {
            r["status"]: r["n"]
            for r in conn.execute(
                f"SELECT status, COUNT(*) AS n FROM audit_events {where} GROUP BY status", params
            )
        }
        top_tools = [
            {"tool_name": r["tool_name"], "count": r["n"]}
            for r in conn.execute(
                f"SELECT tool_name, COUNT(*) AS n FROM audit_events {where} "
                "GROUP BY tool_name ORDER BY n DESC LIMIT 10",
                params,
            )
        ]
        oldest = conn.execute("SELECT MIN(ts) AS t FROM audit_events").fetchone()["t"]
    return {"total": total, "by_status": by_status, "top_tools": top_tools, "oldest_ts": oldest}


def verify_chain() -> dict[str, Any]:
    """Walk the whole chain and report the first broken link, if any.

    Returns ``{"ok": True, "checked": n}`` or ``{"ok": False, "checked": n,
    "broken_at_id": id, "reason": ...}``.
    """
    with _connect() as conn:
        expected_prev = _get_meta(conn, "anchor_hash", GENESIS_HASH)
        checked = 0
        for r in conn.execute("SELECT * FROM audit_events ORDER BY id ASC"):
            row = dict(r)
            if row["prev_hash"] != expected_prev:
                return {"ok": False, "checked": checked, "broken_at_id": row["id"],
                        "reason": "prev_hash does not match the previous row (row deleted or reordered)"}
            if compute_hash(row) != row["hash"]:
                return {"ok": False, "checked": checked, "broken_at_id": row["id"],
                        "reason": "row content does not match its hash (row edited)"}
            expected_prev = row["hash"]
            checked += 1
    return {"ok": True, "checked": checked}
