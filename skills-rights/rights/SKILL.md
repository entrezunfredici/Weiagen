---
name: rights
description: How Hermes's deny-by-default authorization (rights-plugin) gates tool calls and cron jobs, and how to react when one is blocked
---

# Rights Skill

`rights-plugin` is not a set of tools you call — it's an invisible gate in
front of **every** tool call you make (built-in, another plugin's, or
MCP-provided). You don't interact with it directly; you only see its
effects: a tool call you make either runs normally, gets silently allowed,
or comes back refused/paused. This skill explains what those outcomes mean
and how to talk to the user about them.

Every turn, your context also gets an `[identity] platform=... user=...
roles=...` line injected — that's this same system telling you who is
actually talking to you (their platform identity and the role(s) it maps
to). Trust it: it's real, not something the user can spoof by claiming a
role in chat.

Some turns also carry one or more extra lines, `[mcp_identity_token
kid=<kid> label=<label>] <token> — opaque, signed...` — one per external
MCP microservice an operator has configured a signing key for (never a
Hermes plugin; see the dashboard's "MCP signing keys" section or `hermes
rights mcp-key list`). When an MCP tool's own schema declares a parameter
for this (e.g. `caller_token`), match it by **kid**, not just by taking
whichever line happens to be there — the tool's own name/description
should tell you which kid it expects (e.g. a tool from "RAG MCP" expects
the line whose `kid=rag_mcp`). Copy the token **verbatim** into that
parameter. Never edit it, shorten it, retype it from memory, or invent one
when no line matches (it's simply omitted for any MCP without a configured
key — that's normal, not an error). This token, not the plain-text identity
line above, is what that external service actually trusts to make its own
access decision — the plain-text line is informational only and not
something an external MCP should rely on for security.

## Two kinds of gating — know the difference

- **Any other tool** (`shell_exec`, `docs_create_docx`, an MCP tool, …):
  gated as "may this identity execute this tool at all". **Bootstrap
  leniency applies, but only until the very first `hermes_tool` right is
  ever created** — before that, nothing is gated at all (day-one, zero
  config). The moment *any* `hermes_tool` right exists (for any single
  tool, or `*`), every tool call is evaluated for real: a tool with no
  matching right is now **denied**, not left open. So: on a
  freshly-enabled plugin, tools "just work"; on a plugin an admin has
  already started configuring, only tools an active right actually
  covers work — don't assume the rest are still open just because a
  narrow right exists for one specific tool.
- **`cronjob`** (create/list/update/pause/resume/remove a scheduled job):
  gated as real CRUD (`create`/`read`/`update`/`delete`), **with no
  bootstrap leniency**. A cron job plants a persistent, auto-executing
  prompt — a materially more sensitive capability than a single tool call
  — so **"nobody has configured a cron right yet" means denied**, not
  ungated. Expect "I'm not allowed to manage cron jobs yet" to be a
  perfectly normal, common outcome the first time anyone asks for a
  scheduled task, until an admin grants it.

## What a block looks like

A blocked call fails with a message shaped like:

```
Blocked by rights-plugin: No role of this identity (<roles>) is granted '<operation>' on <resource_type>:<resource_id>
```

When you see this:

- **Report it plainly.** Tell the user their current role(s) don't have
  this specific permission — quote the operation and resource type if it
  helps (e.g. "creating cron jobs" for `hermes_cron:*:create`).
- **Never retry the same call hoping it'll go through.** It won't — the
  decision is deterministic on the current identity's roles.
- **Tell them how to fix it**, if they seem like they'd want to: an admin
  grants the right from the dashboard (`Access Groups` tab →
  `hermes_cron` or `hermes_tool` section → "New right"), or via
  `hermes rights right add --roles <role> --resource-type hermes_cron
  --resource-id '*' --create --read --update --delete` (swap the flags
  for whichever operations should be allowed).
- **If a right for the exact right tool/role already looks correct and
  it's still denied**, the CLI/dashboard `fields` value is never the
  cause for `hermes_tool`/`hermes_cron` — it's always forced to `["*"]`
  server-side no matter what's entered (see .agents/DECISIONS.md,
  2026-08-20), so don't suggest checking or changing it.
- **Don't over-invest in gathering details before finding out.** For
  `cronjob` specifically: it's fine to ask what the user wants scheduled,
  but don't spend many turns refining schedule/prompt details before ever
  attempting the call — if there's a good chance this identity has no
  `hermes_cron` right yet, get to the actual attempt reasonably quickly
  so a likely denial surfaces early instead of after a long back-and-forth.

## What an approval escalation looks like

Some rights require confirmation even when allowed. That surfaces through
Hermes's own native human-approval gate (a pause-and-confirm prompt), not
as an error — nothing special for you to do beyond waiting for the
approval like any other confirmation-gated action.

## Resource types at a glance

| `resource_type` | `resource_id` | Operations that matter | Bootstrap leniency |
|---|---|---|---|
| `hermes_tool` | tool name, or `*` | `execute` only | Until the first `hermes_tool` right exists anywhere — then every tool needs its own matching right |
| `hermes_cron` | always `*` (no per-job scoping) | `create`/`read`/`update`/`delete` | None — denied until configured, from the very first call |

Other resource types (`odoo_model`, …) belong to other plugins that
delegate to the same rights system — see their own skills for details.
