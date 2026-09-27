# `audit` — Hermes plugin

Append-only, hash-chained audit log of **every tool call** made through
Hermes (who, which tool, redacted arguments, outcome — including calls
blocked by `rights-plugin`) and **every approval decision**. Stored in a
local SQLite file, read back from the `hermes audit` CLI, the "Audit"
dashboard tab, and an opt-in `audit_search` agent tool.

Stdlib only (no `uv pip install` step). Independent of `rights-plugin`:
it keeps recording even if `rights` is disabled.

## What gets recorded

| Source (Hermes hook) | `event` | `status` values |
| --- | --- | --- |
| `post_tool_call` — fired by Hermes core for **every** outcome of a tool call | `tool_call` | `ok`, `error`, `blocked`, `cancelled`, `timeout` |
| `post_approval_response` — human (or auxiliary-LLM) answer to an approval prompt, for both `rights-plugin` "require confirmation" rules and Hermes's own dangerous-command gate | `approval` | `once`, `session`, `always`, `deny`, `timeout`, `smart_approve`, `smart_deny` |

A call denied by `rights-plugin` shows up as `status=blocked`,
`error_type=plugin_block`, with rights-plugin's reason in `error_message`.
An approval event carries the same `tool_call_id` as the tool call it
gated.

Per event: UTC timestamp, tool name, status, error type/message, duration,
`session_id`/`task_id`/`tool_call_id`/`turn_id`, the caller's
`platform`/`user_id` (resolved from the session, e.g. `slack`/`U0123…`;
empty for cron/system sessions), the redacted arguments, and the **size**
of the result.

**Never stored**: the tool result itself (it can hold business data — Odoo
records, file contents), and secrets in arguments:

- any key that looks like a secret (`password`, `token`, `caller_token`,
  `api_key`, `authorization`, `secret`, `cookie`, …, at any depth) →
  `"[REDACTED]"` — this covers the signed MCP identity token from
  `rights-plugin`;
- every other string goes through Hermes's own `redact_sensitive_text`
  (catches e.g. a bearer token inlined in a shell command);
- strings are cut at 500 characters, the whole argument JSON at 4000.

## Integrity (hash chain)

Each event stores `hash = sha256(prev_hash + content)`. `hermes audit
verify` (or the dashboard's "Verify integrity" button) walks the chain and
reports the first edited, deleted or reordered event.

This detects tampering, it does **not prevent** it: a process with write
access to `audit.db` can rewrite the chain from the tampered event onward,
and truncating the most recent events is not detectable from the file
alone. If the agent can reach `$HERMES_HOME` with a shell/file tool, the
log is only as trustworthy as that access — moving the log out of the
agent's reach (a separate service) is the next step if that matters; see
`.agents/DECISIONS.md` (2026-09-24).

## Storage & retention

- File: `$HERMES_HOME/audit-plugin-data/audit.db` (SQLite, WAL mode).
  Override with `AUDIT_DB_PATH`.
- `AUDIT_RETENTION_DAYS` (default `90`, `0` = keep forever): events older
  than this are deleted at most once a day, on the next write. Purging
  moves the chain's anchor forward, so `verify` stays valid.
- Manual purge: `hermes audit purge --older-than-days N --yes`.

## Enable

```bash
docker exec hermes /opt/hermes/.venv/bin/hermes plugins enable audit
docker restart hermes
```

Same bind mount (`docker-compose.yml`) / `COPY` (`Dockerfile`) pattern as
the other plugins.

## CLI

```bash
hermes audit list [--user U0123] [--platform slack] [--tool 'odoo_sdk_*'] \
                  [--status blocked] [--event tool_call|approval] [--since 24h] [--limit 50]
hermes audit stats [--since 7d]
hermes audit verify
hermes audit purge --older-than-days 180 --yes
```

`--since` accepts `30m`, `24h`, `7d`, `2w` or an ISO date (`2026-09-01`).
`--tool` accepts an exact name or a prefix ending with `*`.

Run it inside the container as the `hermes` user (`docker exec -u hermes
hermes …`): a `purge` run as root leaves root-owned SQLite side files the
gateway can then no longer write (same pitfall as the other plugins).

## Dashboard

"Audit" tab (after "Access Groups"): filters (user, tool, status, since),
per-status counts, a click-to-expand row with the redacted arguments, and a
"Verify integrity" button. Read-only: no delete/purge from the UI.

## Agent tool `audit_search` (opt-in)

Disabled by default. Set `AUDIT_AGENT_TOOL_ENABLED=1` in `.env` and
recreate the container to register it.

⚠️ It shows **everyone's** activity to whoever is talking to the agent. On a
company-wide Slack workspace, only enable it together with a
`rights-plugin` right restricting it to an admin role — and remember that
once any `hermes_tool` right exists, every tool needs its own right (see
`rights-plugin/README.md`):

```bash
hermes rights right add --roles admin --resource-type hermes_tool \
  --resource-id audit_search --execute
```

Parameters: `user_id`, `platform`, `tool_name` (prefix `*` allowed),
`status`, `since` (default `7d`), `limit` (default 20, max 100).

## Layout

```text
audit-plugin/
├── plugin.yaml
├── __init__.py          # register(): hooks, CLI, opt-in tool
├── audit_store.py       # SQLite store: append/query/stats/verify/purge, hash chain
├── audit_redact.py      # argument redaction + size caps
├── audit_identity.py    # session_id -> (platform, user_id), cached
├── cli.py               # `hermes audit ...`
├── tools.py             # `audit_search` (opt-in)
├── dashboard/           # "Audit" tab: manifest.json, plugin_api.py, dist/index.js (hand-written, no build step)
└── tests/               # pytest suite (no Hermes needed)
```

Top-level modules are prefixed `audit_` on purpose: `rights-plugin` already
owns top-level `identity`/`models`/`engine` in the same Hermes process, and
`sys.modules` is a global cache by name.

## Tests

```bash
cd audit-plugin
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```
