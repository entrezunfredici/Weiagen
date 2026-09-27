# rights — Hermes plugin

Generic deny-by-default authorization: identity → role bindings (any
platform Hermes talks to — Slack, Telegram, CLI, … — not hardcoded to one)
and role → resource access rights. Replaces `odoo-plugin`'s `OdooRight`
entirely (see `../.agents/DECISIONS.md`, "rights-plugin: vendoring vs
cross-plugin import") and can gate any Hermes tool call by name — built-in,
another plugin's, or MCP-provided — since Hermes's `pre_tool_call` hook fires
uniformly for all of them. Also exposes the resolved identity to the model's
context on every turn (`pre_llm_call`) so an MCP server whose own tool schema
wants an identity parameter can be given one — this plugin never enforces
anything inside an MCP server itself, that stays each MCP's own concern.

`rights_w_main/errors_manager`, `rights_w_main/data_manager` and
`rights_w_main/right_manager/right_manager.py` here are a deliberate
**vendored copy** of `odoo-plugin`'s `w_main` (not a shared import — see
`../.agents/DECISIONS.md` for why), renamed from `w_main` to
`rights_w_main` so the two vendored copies can never collide in
`sys.modules` when both plugins are loaded in the same Hermes process
(bare `import w_main` is a single global cache key — see
`../.agents/DECISIONS.md`), extended with one addition:
`right_manager.py` gains a 5th operation, `execute`, alongside the original
`create`/`read`/`update`/`delete` — needed because a bare tool call has no
natural CRUD verb, and this plugin's `pre_tool_call` hook needs one to gate
`hermes_tool`/`hermes_cron` resources.

## Install

This directory is bind-mounted directly into the Hermes container by
`../docker-compose.yml` (read-only, at `/opt/data/plugins/rights`) — same
pattern as `odoo-plugin`, see the repo root README.

```bash
docker exec hermes /opt/hermes/.venv/bin/hermes plugins enable rights
docker restart hermes
```

No `uv pip install` step — this plugin has **zero third-party dependencies**
(pure stdlib; its models declare no secret field, so the vendored
`SecretService`'s `keyring`/`cryptography` code paths are never exercised —
see `requirements.txt`).

**`odoo-plugin` requires `rights-plugin` to be enabled too** — without it,
every `odoo_sdk_*` CRUD call fails closed (`ConfigurationError`), by design
(see `../odoo-plugin/w_odoo/rights_bridge.py`). There is no
manifest-declared plugin-dependency mechanism in Hermes today, so this is an
operational requirement to remember, not something enforced automatically at
enable-time.

**`../skills-rights/rights/`** is a normal, always-discoverable Hermes
skill (same mechanism as `../skills-odoo/*`, bind-mounted at
`/opt/data/skills/rights` — see `../.agents/CONVENTIONS.md`) that teaches
the agent how this plugin's gating actually behaves — the `hermes_tool`
vs. `hermes_cron` distinction, what a block/approve response means, and
how to explain a denial to the user instead of retrying or over-asking
for details before ever finding out an action is going to be refused
(added 2026-08-19 after exactly that happened in production — see
`../.agents/DECISIONS.md`).

## Role catalog

Roles are managed independently of who holds them (role bindings, below)
or what they grant (access rights, below) — a small catalog of
`(id, label, description)` entries, purely organizational: nothing
enforces that a role string used elsewhere actually has a catalog entry
(see `models.py`'s module docstring), it just gives the dashboard's
pickers something to offer and a place to attach a human-readable name.
`"everyone"` and `"automation"` — the two implicit pseudo-roles every
identity/session always carries (see "Authorization model" below) — are
seeded automatically, along with a catalog entry for every role string
already in use anywhere, the first time the plugin loads after an
upgrade (`models.py::seed_role_catalog`, idempotent, never overwrites an
existing label).

```bash
docker exec hermes /opt/hermes/.venv/bin/hermes rights role catalog create \
  --id admin --label "Administrateur" --description "Full access"

docker exec hermes /opt/hermes/.venv/bin/hermes rights role catalog list
docker exec hermes /opt/hermes/.venv/bin/hermes rights role catalog rm admin
```

## Configure identity→role bindings and access rights

```bash
# Bind a Slack user to one or more roles.
docker exec hermes /opt/hermes/.venv/bin/hermes rights role bind \
  --platform slack --user U0123ABC --roles admin,finance --label "Fred"

docker exec hermes /opt/hermes/.venv/bin/hermes rights role list

# Grant the "admin" AND "finance" roles execute access on a specific Hermes
# tool — one right, several roles (--roles is plural/comma-separated since
# 2026-08-18, a signalled breaking change from the old singular --role).
docker exec hermes /opt/hermes/.venv/bin/hermes rights right add \
  --roles admin,finance --resource-type hermes_tool --resource-id shell_exec --execute

# Grant the "everyone" role read+create on an Odoo model (mirrors what
# odoo-plugin's own rights used to look like before this plugin existed —
# resource_id embeds the Odoo profile id by odoo-plugin's own convention,
# this plugin treats it as an opaque string).
docker exec hermes /opt/hermes/.venv/bin/hermes rights right add \
  --roles everyone --resource-type odoo_model --resource-id "default:project.task" \
  --fields '*' --read --create --require-confirmation

docker exec hermes /opt/hermes/.venv/bin/hermes rights right list

# Debug, no side effects:
docker exec hermes /opt/hermes/.venv/bin/hermes rights whoami --platform slack --user U0123ABC
docker exec hermes /opt/hermes/.venv/bin/hermes rights check \
  --roles admin,everyone --resource-type hermes_tool --resource-id shell_exec --operation execute
```

Role bindings and access rights are stored under
`$HERMES_HOME/rights-plugin-data/` (JSON files, no secrets involved),
deliberately **not** under `plugins/rights/` since that directory is the
read-only bind-mounted plugin source — same layout convention as
`odoo-plugin`.

**Same `docker exec`/ownership pitfall as `odoo-plugin`** (see its
README): the gateway/dashboard processes run as the `hermes` user
(uid from `HERMES_UID`), but a bare `docker exec hermes ...` runs as
**root** by default. A root-owned write under `rights-plugin-data/`
(e.g. running `hermes rights directory sync`/`role bind`/`right add` via a
plain `docker exec`) makes that file unreadable by the `hermes`-user
gateway process — silently, since `directory.py::ensure_fresh` swallows
the resulting `PermissionError`/`ServiceError`, so the only visible symptom
is a `PermissionError` traceback repeating in `errors.log`/`agent.log` on
every turn, not a crash. Either add `-u hermes` to the `docker exec`, or run
`docker exec hermes chown -R hermes:hermes /opt/data/rights-plugin-data/`
afterward (hit for real on `test-server`, 2026-08-17 — see `.agents/CHANGELOG_AGENT.md`).

## Authorization model

Every operation is **deny-by-default**, evaluated per `(role, resource_type,
resource_id, field, operation)`, generalizing `odoo-plugin`'s old
`(profile, model, field, operation)`:

- An identity's roles always include the implicit `everyone` role, plus
  `automation` when no platform identity resolves at all (e.g. a
  cron-triggered session — see `identity.py`).
- A single `AccessRight` can itself apply to **several roles at once**
  (`roles: list`, since 2026-08-18 — was a single `role: str`) instead of
  needing a duplicate right per role — pure convenience, no change to the
  decision logic itself: it's exactly equivalent to creating one right per
  listed role with otherwise identical fields/CRUD/confirmation.
- **Multi-role combination is "most permissive wins"**, decided explicitly
  (not a full RBAC lattice with deny-overrides): an operation is allowed if
  *any* of the identity's roles grants it; confirmation is required only if
  *every* granting role requires it. A role meant to be more restrictive
  will not restrict an identity that also holds a more permissive role — a
  known, deliberate v1 simplification.
- `resource_id` supports an exact match or a `"*"` wildcard (any resource of
  that type); `fields` supports the same `"*"` wildcard per right, exact
  field matches are preferred over wildcard matches, and exact
  `resource_id` matches are preferred over a wildcard `resource_id` (see
  `engine.py::_choose_candidate`).
- A right can require confirmation (`--require-confirmation` /
  `--confirm-<op>` at the CLI). For tools gated via this plugin's own
  `pre_tool_call` hook, that's enforced as a real `{"action": "block", ...}`
  hard denial when not allowed at all, or an `{"action": "approve", ...}`
  escalation to Hermes's native human-approval gate when allowed but
  unconfirmed — confirmed directly against Hermes core's
  `hermes_cli.plugins._get_pre_tool_call_directive_details` contract (see
  `../.agents/DECISIONS.md`). For `odoo-plugin`'s own tools, the check is
  the same decision, consumed through `rights_plugin_api.check_right()`
  instead of this plugin's own hook.

## MCP identity tokens for external microservices (`token_signer.py`)

`pre_llm_call`'s plain-text `[identity] platform=... user=... roles=...`
context line (above) is fine for an MCP tool schema that just wants a hint,
but it isn't enough for an **external** MCP microservice (a separate
process/host, never a Hermes plugin — e.g. a self-hosted service like
`rag_mcp`) that wants to make a real access-control decision from it: the
LLM is the only transport between Hermes and that service, and can't be
trusted not to garble or fabricate role names on the way. This plugin never
enforces anything inside an MCP server itself — see "Authorization model"
above — but it can hand the LLM something the MCP server can trust *despite*
going through the LLM: a signed, opaque token, one per external MCP.

**One signing key per external MCP (`models.McpSigningKey`), managed as
data, not a docker-compose env var.** Each external microservice gets its
own `(kid, secret)` pair, added/edited/revoked from the dashboard's "MCP
signing keys" section or `hermes rights mcp-key add/list/reveal/rm` — like
every other table in this plugin, the registry is read fresh on every call
(no in-memory caching, see [[rights-plugin-gating-gotchas]]), so adding or
rotating a key **never requires a container restart**. A leaked/rotated key
for one MCP never affects any other.

Because a turn doesn't know in advance which external MCP tool (if any) the
model is about to call, `_pre_llm_call` signs and injects **one token per
active key**, each labelled by its `kid`/`label` so the model can match it
to the right MCP tool's schema:

```text
[mcp_identity_token kid=rag_mcp label=RAG MCP] <token> — opaque, signed.
Pass it UNCHANGED as the identity/caller-token argument of the external MCP
tool whose schema/description names this kid. Never edit, shorten, or
fabricate this value.
```

The token itself is a hand-rolled, JWT-shaped compact string
(`base64url(header).base64url(payload).base64url(signature)`, no
third-party dependency — keeps this plugin's stdlib-only convention):

- `header`: `{"alg": "HS256", "kid": "..."}` — the external MCP verifies
  according to *this*, never a hardcoded algorithm, so a future migration to
  asymmetric signing doesn't break already-deployed verifiers overnight (see
  below).
- `payload`: `{"iss": "hermes-rights-plugin", "sub": "<platform>:<external_user_id>",
  "roles": [...], "iat": ..., "exp": ...}` — short-lived (5 minutes by
  default, `RIGHTS_MCP_TOKEN_TTL_SECONDS` env var — a policy knob, not a
  secret, so it stays in `docker-compose*.yml`), because this is a bearer
  credential relayed through a slow, log-heavy transport (the LLM), not
  because of expected clock skew.
- Signed with HMAC-SHA256 today, using that key's own secret — shown in
  full exactly once, right after creation/rotation (dashboard response /
  CLI output), masked (last 4 characters only) in every listing after that.
  A blank `--secret` on `mcp-key add` auto-generates one for a brand new
  kid, or keeps the existing secret unchanged when editing an existing kid.

**Opt-in and silent when unconfigured**: an empty registry (no key created
yet) means `issue_mcp_identity_tokens()` returns `[]` and no extra context
line is appended — deploying/upgrading this plugin must never inject
garbage or break a turn by surprise, same bootstrap-safety philosophy as
every other gate in this plugin.

**Planned migration to EdDSA (Ed25519)**: `McpSigningKey.alg` selects the
signer per key (`"HS256"` today; an `"EdDSA"` entry is added to
`token_signer._SIGNERS` when the migration lands — needs the `cryptography`
package, an interface/dependency change to signal explicitly first, see
`../.agents/AGENT.md`). A key already saved with `alg="EdDSA"` ahead of that
code landing is simply skipped (logged), never mis-signed as HMAC — `_save_mcp_signing_key`
also validates `alg` against `token_signer.SUPPORTED_ALGS` at write time.
Asymmetric signing means a compromised external MCP can no longer forge
tokens for the others, only verify — each MCP only ever needs the **public**
key, not a shared secret. The token `header`'s `alg`/`kid` fields exist
specifically so external verifiers, written against today's `HS256` tokens,
can add an `EdDSA` branch ahead of time and keep working unchanged through
the cutover (roll out EdDSA-aware verifiers to every MCP *before* switching
any key's `alg` here — never the other way around).

**What this plugin does *not* do**: verify the token, decide what a given
role may do inside an MCP, or know anything about any specific MCP
service's own ACL. That logic — and the secret/public key it needs to check
the signature — lives entirely in each external MCP's own codebase, outside
this repo.

```bash
# Auto-generates a secret, prints it once — copy it now, share out-of-band.
docker exec hermes /opt/hermes/.venv/bin/hermes rights mcp-key add \
  --id rag_mcp --label "RAG MCP (self-hosted)"

docker exec hermes /opt/hermes/.venv/bin/hermes rights mcp-key list  # secret shown masked

# Lost the copied secret? Show it again (not logged by default):
docker exec hermes /opt/hermes/.venv/bin/hermes rights mcp-key reveal rag_mcp

# Rotate: pass --secret explicitly, or omit it on `add` to keep the current one.
docker exec hermes /opt/hermes/.venv/bin/hermes rights mcp-key add --id rag_mcp --secret "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

docker exec hermes /opt/hermes/.venv/bin/hermes rights mcp-key rm rag_mcp
```

Same operations from the dashboard's "MCP signing keys" section (below the
Access rights groups) — "New key" / "Edit" / "Reveal" / "Delete" buttons
over the same `RightsConfigExecutor` actions.

## `hermes_tool` and `hermes_cron`: what CRUD/execute actually gate

Two built-in `resource_type`s are wired to real enforcement in
`_pre_tool_call` (`__init__.py`), everything else is generic:

- **`hermes_tool`** (`resource_id` = a tool name, or `"*"` for any tool):
  only the **`execute`** operation is meaningful — a bare tool call has no
  CRUD verb of its own, `execute` is this plugin's stand-in for "may run
  this tool at all" (see the vendored `right_manager.py`'s 5th operation,
  above). `create`/`read`/`update`/`delete` are accepted by the data model
  for uniformity but never consulted for this type. **Bootstrap safety
  gate**: no tool is gated until the *very first* `hermes_tool` right
  exists anywhere — enabling this plugin with zero rights configured must
  never start denying every built-in tool by surprise. But this leniency
  is per-`resource_type`, not per-tool (fixed 2026-08-19, was a real
  production bug — see `.agents/DECISIONS.md`): the moment **any**
  `hermes_tool` right exists, even one scoped to a single tool, deny-by-
  default kicks in for *every* tool, not just the ones with a matching
  right. In practice: keep a `resource_id: "*"` right around for whatever
  should stay broadly usable, and add narrower rights on top of it for
  anything you want to single out — narrowing your only right down to one
  tool does not "restrict to that tool", it locks out everything else.
- **`hermes_cron`** (`resource_id` is always `"*"` — there is no per-job
  granularity, this is a coarse capability, not a per-job ACL): a real
  CRUD right. Every call to Hermes's unified `cronjob` tool is redirected
  here instead of the generic `hermes_tool` path, with the operation
  derived from its `action` argument: `create`→`create`, `list`→`read`,
  `update`/`pause`/`resume`→`update`, `remove`→`delete` (anything
  unrecognized defaults to `read`, the least destructive verb). This only
  exists because `cronjob` is itself a single tool multiplexing all cron
  operations behind one `action` parameter — confirmed by reading
  `tools/cronjob_tools.py` directly, since Hermes has **no dedicated cron
  hook** (`hermes_cli/plugins.py::VALID_HOOKS`) to gate this any other
  way. Before 2026-08-19 this resource type was a dead placeholder: it
  showed up in the dashboard but nothing ever enforced it. **Does NOT get
  `hermes_tool`'s bootstrap safety gate** (fixed 2026-08-19, caught in
  production the same day the CRUD mapping shipped): with zero
  `hermes_cron` rights configured, cron calls are **denied**, not
  ungated — a cron job can plant a persistent, auto-executing prompt, a
  materially more sensitive capability than a single tool call, so
  "nobody configured this yet" means denied here, unlike `hermes_tool`.
- **`fields` is always forced to `["*"]` for both** (fixed 2026-08-20,
  a real production bug — see `.agents/DECISIONS.md`): a bare tool or
  cron call has no "fields" the way an Odoo model record does, so this
  is not a thing you can meaningfully scope. `models.create_access_right`
  overrides whatever is submitted, regardless of entry point (dashboard,
  CLI, `rights_plugin_api`) — a right whose `fields` isn't `["*"]` is
  100% inert for `hermes_tool`/`hermes_cron` (`check_right` always
  evaluates them with `field="*"`, and a right only covers `"*"` when
  `"*"` is literally in its `fields`), so a right you think you've
  "scoped to one tool" via this field instead silently denies
  *everything*, including that tool. The dashboard doesn't even show
  this field for these two types. Rights saved before this fix are
  self-healed automatically at plugin load (`models.
  normalize_hermes_resource_fields`, same pattern as the OdooRight
  migration) — no manual data edit needed.
- A right's `rule_key` (used when Hermes escalates to human approval) is
  `rights:{resource_type}:{resource_id}:{operation}` (operation included
  since 2026-08-19) — for `hermes_cron`, the same resource (`"*"`) can be
  create/read/update/delete on different calls, so an "always approve"
  decision on one operation must never silently cover the others.

`hermes rights tools` / `GET /hermes-tools` list every tool Hermes
currently has registered (name, toolset, description), read live from
Hermes core's own `tools.registry.registry` singleton — pure UI
convenience (feeds the dashboard's tool picker for `hermes_tool` rights,
see below), never consulted by the decision engine itself. Returns `[]`
if the real registry isn't importable (e.g. outside a real Hermes
process — the test environment stubs `tools.registry` without a
`registry` attribute on purpose, see `tools_catalog.py`).

```bash
docker exec hermes /opt/hermes/.venv/bin/hermes rights tools

# Give "admin" full cron CRUD:
docker exec hermes /opt/hermes/.venv/bin/hermes rights right add \
  --roles admin --resource-type hermes_cron --resource-id '*' \
  --create --read --update --delete
```

## Slack member directory (pick-list, not part of the authorization model)

Binding a role to a Slack user needs their raw Slack user id (`U0123ABC`) —
tedious to copy/paste by hand from a profile page every time. This plugin
caches the Slack workspace's member list (id → display name) and offers it
as a pick-list in the dashboard's "New role binding" form instead:

```bash
# Force a real sync now (loud on failure — bad/missing SLACK_BOT_TOKEN,
# missing users:read scope, Slack outage all raise visibly):
docker exec hermes /opt/hermes/.venv/bin/hermes rights directory sync

# Show what's currently cached (no network call, no side effects):
docker exec hermes /opt/hermes/.venv/bin/hermes rights directory list
```

Reuses the **same** `SLACK_BOT_TOKEN` Hermes's own Slack platform adapter
already gets from `.env`/`docker-compose*.yml` — this plugin manages no
Slack credentials of its own, and needs no new dependency (`slack_directory.py`
talks to `https://slack.com/api/users.list` directly via stdlib `urllib`).

There's no Hermes plugin API to register a periodic background job (only
`pre_tool_call`/`pre_llm_call` hooks and CLI commands), and near-real-time
freshness doesn't matter here ("ça change pas beaucoup"), so refresh is
**lazy**: every read of the cache (the dashboard's `GET /directory`, and
this plugin's own `pre_llm_call` hook, which already fires once per turn)
opportunistically re-syncs only once the cache is older than 24h — cheap
(one timestamp comparison) on every turn that isn't stale, and a real sync
failure there is swallowed, never raised (see `directory.py::ensure_fresh`).
The dashboard also has an explicit "Refresh now" button (`POST
/directory/sync`) that surfaces failures loudly instead.

Purely a UX convenience — `engine.py`'s authorization decisions never
consult this cache, and a stale/empty directory never affects what anyone
is actually allowed to do, only how tedious binding a new role is.

## Connected-platform picker (`platforms.py`)

The dashboard's "New role binding" form offers a **platform picker**
(instead of free-typing "slack") populated from whichever messaging
platforms Hermes itself looks configured for on this deployment — the same
env-var-presence check `hermes status` uses under "Messaging Platforms"
(hand-kept copy of that exact mapping, see `platforms.py`'s docstring for
why it isn't imported from Hermes core). CLI equivalent:

```bash
docker exec hermes /opt/hermes/.venv/bin/hermes rights platforms
docker exec hermes /opt/hermes/.venv/bin/hermes rights platforms --all  # include unconfigured ones too
```

Once a platform is picked, if a directory is cached for it (Slack today —
see above), users appear as clickable tags instead of a plain dropdown, with
a filter box once there are more than a handful. Picking a tag fills the
user id (and label, if empty) the same way the old dropdown did.

## Dashboard

`dashboard/` is a Hermes **dashboard** plugin — independent of the
`plugin.yaml`/`register(ctx)` tool-plugin system above, discovered from
`dashboard/manifest.json` and mounted by the dashboard host process
(vanilla IIFE, same pattern as `odoo-plugin/dashboard/`, see
`../.agents/DECISIONS.md`). Opening `http://127.0.0.1:9119` shows an
**"Access Groups"** tab after "Odoo":

- **Roles section**: create/delete role catalog entries (`id`/`label`/
  `description`) — the same data `hermes rights role catalog create/rm`
  manages. Shown first: role bindings and rights below pick from this
  catalog. Each role also lists who currently holds it (computed
  client-side from the same bindings the section below fetches) and lets
  you add/remove people **from the role itself** — removing someone here
  only drops that one role from their binding (their other roles are
  left alone, unless it was their last one, in which case the binding is
  unbound outright); adding someone merges into whatever binding they
  already have rather than replacing it. Same `/role-bindings` endpoint
  under the hood as the section below, just a role-centric view of the
  same data instead of a person-centric one.
- **Role bindings section**: bind/unbind an identity (`platform` +
  `external_user_id`) to one or more roles, picked as clickable tags from
  the catalog above (`RoleTagPicker`, toggle multi-select) instead of a
  free-text field — the same data `hermes rights role bind/unbind`
  manages. When the typed platform is `slack`, a "Pick from directory"
  dropdown (see "Slack member directory" above) lets an admin choose a
  name instead of typing a raw Slack id, plus a status row showing member
  count / last sync time and a "Refresh now" button.
- **Access rights section**: grouped dynamically **by `resource_type`**,
  one block per type, so Hermes's own general access groups
  (`hermes_tool`, `hermes_cron` — always shown, even empty, so it's obvious
  where to configure access to built-in tools/crons) sit alongside sections
  contributed by any plugin that delegates to `rights-plugin` (`odoo_model`
  today, from `odoo-plugin`). There is no cross-plugin UI-composition
  mechanism in Hermes today (see `../.agents/DECISIONS.md`, 2026-08-14) — a
  new `resource_type` shows up here automatically the moment a right exists
  for it, no code change needed in this dashboard. Its form also picks
  roles as tags from the catalog (a right can apply to several roles at
  once). The form itself adapts to `resource_type` (see "`hermes_tool` and
  `hermes_cron`" above for what CRUD/execute actually mean per type):
  `hermes_tool` swaps the free-text "Resource id" for a `<select>` of live
  Hermes tools (`GET /hermes-tools`, grouped by toolset) and shows only the
  `execute` checkbox; `hermes_cron` fixes "Resource id" to `"*"`
  (read-only, no per-job scoping) and shows only `create`/`read`/`update`/
  `delete`; any other `resource_type` keeps the original free-text field
  and all five checkboxes.
- **MCP signing keys section**: separate from the CRUD above — one row per
  `models.McpSigningKey` (kid, label, algorithm, masked secret, active
  toggle), "New key"/"Edit"/"Reveal"/"Delete" over the same actions
  `hermes rights mcp-key ...` uses. See "MCP identity tokens for external
  microservices" above for what these keys are for.

**Source layout (`dashboard/src/` → `dashboard/dist/index.js`)**: `entry`
in `manifest.json` names exactly one file, and the dashboard host loads it
via a classic `<script src>` (no ES module `import`/`export` across
files, no runtime multi-file loading — confirmed by reading
`hermes_cli/web_server.py` directly, see `../.agents/DECISIONS.md`,
2026-08-18). So the component code is written as six separate,
readable source files under `dashboard/src/` (`00-core.js`, `01-roles.js`,
`02-role-bindings.js`, `03-access-rights.js`, `04-mcp-keys.js`, `05-page.js`
— the numeric prefixes are the concatenation order, matching the page's own
reading order), and `dashboard/build.sh` (`cat`, no Node/npm needed)
assembles them into the single `dashboard/dist/index.js` actually served —
that file is **generated**, never hand-edited. All six source files share
one closure (`00-core.js` opens the IIFE, `05-page.js` closes it), so a
standalone syntax check on any one of them will show unbalanced braces —
expected, they're fragments, not modules. **After editing anything under
`src/`, run `./dashboard/build.sh` before testing/deploying.** Two
guardrails catch a forgotten rebuild: `.github/workflows/ci.yml`'s
`test-rights-plugin-dashboard-build` job fails if the committed
`dist/index.js` drifts from `src/`, and the server-deploy `Dockerfile`
regenerates `dist/index.js` from `src/` at image-build time regardless
(a server target typically has no repo checked out and never runs
`build.sh` itself — so this is what guarantees it always gets a fresh
bundle).
- Backed by `dashboard/plugin_api.py` (FastAPI router, mounted at
  `/api/plugins/rights`), which is a thin HTTP layer over the same
  `RightsConfigExecutor` the CLI uses — reading or writing here is
  identical to `hermes rights ...`, just a different front door onto the
  same storage.

`odoo-plugin`'s own dashboard tab keeps a richer, Odoo-scoped editing
experience for its own rights (live Odoo-model dropdown) — it writes
through `rights_bridge.create_right`/`delete_right` into this same
`AccessRight` storage, so a right created there shows up here too (grouped
under `odoo_model`), and vice versa. See `../odoo-plugin/README.md`.

## Tests

`tests/` is a `pytest` suite covering the vendored `rights_w_main` copy (smoke
tests proving it behaves identically to `odoo-plugin`'s), the models
(`RoleBinding`/`AccessRight`), the decision engine, identity resolution, the
hooks, the CLI, and the public `rights_plugin_api` surface — no real Hermes
install needed (`hermes_constants`/Hermes's native `tools` package/
`hermes_state.SessionDB` are all faked, see `tests/conftest.py`):

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

Runs automatically in GitHub Actions on every push/PR (`../.github/workflows/ci.yml`). See
`tests/pytest.ini` for why that file has to live in `tests/` specifically —
same pytest `Package`-collection gotcha as `odoo-plugin`, see
`../.agents/DECISIONS.md` (2026-08-06).
