---
name: mcp-tool-discovery
description: "Trust the live MCP tool catalog over any written skill when using tools from a connected MCP server — and never author a connector-specific procedural skill for one."
version: 1.1.0
author: Fred
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [mcp, tools, discovery, skills, best-practices, tool-calling, self-authoring]
    related_skills: [hermes-agent]
---

# MCP Tool Discovery: Live Catalog Over Written Skills

Hermes' native MCP client connects to every server listed in `mcp_servers`
(`~/.hermes/config.yaml`) at startup, calls `list_tools()`, and registers each
tool as a first-class tool named `mcp_{server_name}_{tool_name}` — see the
`hermes-agent` skill's `references/native-mcp.md` for the full mechanism.
This means, for any connected MCP server, **the tool names, parameters, and
descriptions already sitting in your current tool list are the only
authoritative source.** No separate "discovery step" is required to make
tools usable — they are already there, alongside built-ins like `terminal`
or `read_file`.

## Rule 0: Do Not Author a Procedural Skill for an MCP Connector

**Before writing or saving any skill that documents how to use a specific
MCP server's tools — stop. You almost certainly should not.**

This applies whether you're reacting to a user request, wrapping up a
session, or persisting something you "learned how to do." A skill whose
entire purpose is "here's how to call the tools of MCP server X" duplicates
information that is *already live* in your tool list, and will drift out of
sync the moment the server's tools change — turning from redundant into
actively wrong. This exact anti-pattern has already recurred more than once
in this environment for the same server (see Lesson Learned below), even
after the first bad copy was found and disabled: a fresh one was
self-authored again from scratch in a later session, name-for-name.

Legitimate skill content about an MCP-backed capability is limited to
**judgment calls that survive the tool catalog changing** — e.g. "when a
user asks to ingest a URL, confirm the target collection with them first,
large crawls can take minutes" — never tool names, parameter lists, or
step-by-step call sequences. If you can't describe the "skill" without
naming a specific `mcp_{server}_{tool}`, it isn't a skill, it's a stale copy
of `list_tools()` waiting to happen. Don't write it. If you already started
writing one, delete it instead of saving it.

## When to Use (the rest of this skill)

- You're asked to use a tool belonging to any MCP server (e.g. `rag_mcp`,
  `github`, `filesystem`, or any server the user has connected).
- A written skill and your live tool list disagree about a tool's name,
  parameters, or behavior.
- You're tempted to write down what a connector's tools are called — see
  Rule 0 above first.

## The Rule

1. **Look at your actual tool list first.** Every tool from a connected
   server already appears with the prefix `mcp_{server}_*`. That prefix
   listing *is* the live catalog — don't assume you need to "discover" it
   through a special call.
2. **Read the tool's own `description` and parameter schema.** That's where
   the server author put usage guidance (what it does, when to use it,
   what the arguments mean). Treat it as more current than any prose in a
   skill file.
3. **If the server exposes its own meta/help tool** (e.g. `mcp_{server}_help`,
   `mcp_{server}_list_tools`), and something is still ambiguous, call that
   live helper — it reflects the server's actual current state, not a
   snapshot someone wrote down earlier.
4. **Never call a tool name that isn't in your tool list**, even if a skill
   document mentions it. A skill is a hint about workflow and judgment; the
   live tool registry is ground truth. If a skill's example tool name
   doesn't match anything you actually have, the skill is stale — don't
   improvise a plausible-looking name to match it, and don't leave the
   stale skill in place either (see Rule 0).

## Anti-Pattern (Lesson Learned)

A self-authored skill documented a specific MCP server's tools with
hardcoded example names (`crawl_url`, `add_document`, `list_documents`, ...)
guessed at rather than read from the server's actual live tool list. When
the real tools didn't match, the agent still preferred the skill's static,
keyword-matched documentation over just looking at its own tool list —
including ignoring a real, working help tool the server exposed. The skill
was disabled.

**It came back.** In a later session, without the disabled skill visible
and with no instruction to do so, the agent authored a new skill under the
same name, for the same server, from scratch — this time it did correctly
call the live discovery tool and got the real tool names right in a
reference file, but it *also* rewrote the same kind of tool-by-tool
procedural body as before, alongside them. Getting the names right on a
given day doesn't fix the underlying habit: writing this kind of skill at
all is what causes the drift, not just getting a name wrong once. That's
why Rule 0 exists as its own rule instead of "verify names before writing" —
verifying helps for one snapshot in time; not writing a connector-specific
procedural skill in the first place is what actually holds up.
