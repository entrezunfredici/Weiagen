# odoo — Hermes plugin

Deny-by-default Odoo connector (bounded CRUD gated by per-field rights).
Office document generation (xlsx/docx/pptx) moved to the separate
[`docs` plugin](../docs-plugin/README.md) on 2026-09-24. This is a
Hermes-native port of an OpenClaw plugin (`../sdk-plugin` in this repo's
history) — the domain logic (`w_main/`, `w_odoo/`) is unchanged; only the
integration layer changed (in-process tool calls instead of a subprocess/
JSON bridge, Hermes's native approval gate instead of a bespoke REST-poll
confirmation popup, a CLI *and* a dashboard tab instead of a browser panel).

**Rights are no longer owned by this plugin.** Authorization is delegated
to the sibling `../rights-plugin/` (generic identity→role→resource deny-by-
default engine, usable by any plugin/tool, not just Odoo) via
`w_odoo/rights_bridge.py` — see `.agents/DECISIONS.md` ("rights-plugin:
vendoring vs cross-plugin import"). **`rights-plugin` must always be
enabled alongside this plugin** — without it, every `odoo_sdk_*` CRUD call
fails closed (`ConfigurationError`).

## Install

This directory and `../skills-odoo/*` are bind-mounted directly into the
Hermes container by `../docker-compose.yml` (read-only, at
`/opt/data/plugins/odoo` and `/opt/data/skills/<name>`) — see the repo root
README. A symlink-based install was tried first and turned out to be broken:
a symlink written inside the `~/.hermes` volume that points outside it does
not resolve inside the container's own mount namespace (see
`.agents/DECISIONS.md`).

Once the container is up, from the host:

```bash
docker exec hermes uv pip install --python /opt/hermes/.venv/bin/python \
  -r /opt/data/plugins/odoo/requirements.txt

docker exec hermes /opt/hermes/.venv/bin/hermes plugins enable odoo
docker exec hermes /opt/hermes/.venv/bin/hermes plugins enable rights
docker restart hermes
```

(`rights` is `../rights-plugin/` — see "Authorization model" below. Both
must be enabled; `odoo` alone fails closed on every CRUD call.)

(There's no manifest-declared dependency-install mechanism in Hermes's
plugin system today — this is a manual step. It also does **not** persist
across `docker compose up -d --force-recreate` since the venv lives in the
container's own filesystem layer; re-run it after any recreate. This has
already bitten us more than once this session — see `.agents/DECISIONS.md`.)

**Note on `docker exec` and file ownership**: the dashboard/gateway
processes run as the `hermes` user inside the container (uid from
`HERMES_UID`), but a bare `docker exec hermes ...` runs as **root** by
default. A root-owned write under `$HERMES_HOME/odoo-plugin-data/` (profiles/
rights/keyring) makes those files unreadable by the `hermes`-user processes
("Unable to read data file" in the dashboard). After any `docker exec`
command (without `-u hermes`) that touches that directory, run:
`docker exec hermes chown -R hermes:hermes /opt/data/odoo-plugin-data/`.
(`uv pip install` itself needs to run as root — the venv's `site-packages`
is root-owned — so don't add `-u hermes` there.)

## Configure a connection profile, and rights

Connection profiles are still owned by this plugin. **Rights are managed
through `rights-plugin`** — via its own CLI (the generic, canonical path)
or through this plugin's dashboard tab (a richer, Odoo-scoped editing
experience layered on top, writing the same underlying data — see
"Authorization model" below).

Via CLI:

```bash
docker exec hermes /opt/hermes/.venv/bin/hermes odoo profile add default \
  --base-url https://mycompany.odoo.com --database mycompany \
  --login api-bot --password '...'

docker exec hermes /opt/hermes/.venv/bin/hermes rights right add \
  --role everyone --resource-type odoo_model --resource-id "default:project.task" \
  --fields '*' --read --create --require-confirmation

docker exec hermes /opt/hermes/.venv/bin/hermes odoo profile list
docker exec hermes /opt/hermes/.venv/bin/hermes odoo right list   # read-only view, odoo-shaped
docker exec hermes /opt/hermes/.venv/bin/hermes rights right list --resource-type odoo_model
docker exec hermes chown -R hermes:hermes /opt/data/odoo-plugin-data/ /opt/data/rights-plugin-data/
```

`hermes odoo right add/rm` **no longer exists** — a breaking CLI change,
see "Authorization model" below and `.agents/CHANGELOG_AGENT.md`
(2026-08-13/14).

Or via the dashboard: open `http://127.0.0.1:9119`, an **"Odoo"** tab
appears after "Skills" (see `dashboard/` — a Hermes dashboard plugin,
independent of the `plugin.yaml`/`register(ctx)` tool-plugin system,
discovered from `dashboard/manifest.json` and backed by
`dashboard/plugin_api.py`, a FastAPI router the host mounts at
`/api/plugins/odoo`). Its Rights section keeps full add/edit/delete
capability (live Odoo-model dropdown) — under the hood it now writes
through `rights_bridge.py` into `rights-plugin`'s storage instead of owning
the data itself. A generic **"Access Groups"** tab (from `../rights-plugin/`)
also shows the exact same rights, grouped by resource type alongside every
other plugin's and Hermes's own (tools/crons) — same data, two views.

Profiles and rights are stored under `$HERMES_HOME/odoo-plugin-data/` (JSON
files + a file-based secret keyring — see
`w_main/data_manager/secret_service.py`), deliberately **not** under
`plugins/odoo/` since that directory is the read-only bind-mounted plugin
source. Secrets never go through `config.yaml`.

Secret lookup falls back, in order, to the file keyring → the
`ODOO_SECRET_<REF>` env var → the OS system keyring (macOS Keychain, GNOME
Keyring, KWallet). The container this plugin runs in (like the CI runner)
has no system keyring backend installed, so that last fallback resolves to
"not found" rather than erroring — see `.agents/DECISIONS.md` (2026-08-06)
if you're extending `SecretService` and need the exact contract.

### Encryption at rest

Secret values (Odoo passwords) in the file keyring are encrypted with
Fernet (AES-128-CBC + HMAC) when `ODOO_PLUGIN_ENCRYPTION_KEY` is set —
without it, they're stored in **plaintext JSON**, protected only by file
permissions (`chmod 600`). Generate a key and add it to `.env`:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Existing plaintext entries are migrated transparently the first time
they're read after the key is configured (no separate migration command).
**Losing this key makes existing encrypted secrets unrecoverable** — back it
up alongside the rest of `.env` (never commit either).

## Authorization model

Every operation is **deny-by-default**, evaluated per `(role, resource_type=
"odoo_model", resource_id=f"{profile_id}:{model}", field, operation)` —
generalized from the old per-plugin `(profile, model, field, operation)` to
add a **role** dimension, resolved from the calling identity (e.g. the
Slack user who sent the message). This plugin owns none of that logic
anymore; `w_odoo/rights_bridge.py` is the only place it talks to
`rights-plugin`, via the stable `rights_plugin_api` contract:

- `odoo_sdk_read/create/update/delete` only touch fields a right explicitly
  allows **for the caller's roles**; everything else is silently dropped
  (not an error). `odoo_sdk_list_allowed_models`/`odoo_sdk_list_allowed_fields`
  are likewise scoped to the caller's roles now, not "everything this
  profile is configured for" like before roles existed.
- A right can require confirmation (`--require-confirmation` at the CLI). At
  runtime this is enforced by the plugin's `pre_tool_call` hook (see
  `__init__.py::_pre_tool_call`, now resolving the caller's identity from
  `session_id` before checking), which returns an `approve` directive to
  Hermes's native human-approval gate — the same mechanism Hermes uses for
  dangerous shell commands. There is no separate popup/REST endpoint to run.
- If nobody is bound to a specific role, every identity still implicitly
  holds the `"everyone"` role — existing rights created before roles
  existed were migrated to `"everyone"` automatically (see
  `../rights-plugin/migrate_odoo_rights.py`), preserving exactly the access
  everyone already had.

See `../skills-odoo/odoo-sdk/SKILL.md` for the full agent-facing usage guide,
error codes, and per-model safety notes, and `../rights-plugin/README.md`
for the full generic authorization model (multi-role combination rule,
resource wildcards, etc.).

## Content formatting (`html` fields)

`odoo_sdk_create`/`odoo_sdk_update` normalize plain text written to
Odoo `html`-type fields (e.g. `project.task.description`) before sending it:
`\n` line breaks are converted to `<p>`/`<br/>` (Odoo does not interpret raw
`\n` in html fields — it renders literally). Any value that already contains
recognizable HTML tags is passed through unchanged, so the agent can write
real markup (`<b>`, `<ul><li>`, `<h2>`, `<a href="...">`) to style content.
See `w_odoo/odoo_html.py`.

## Tools

`odoo_config_validate`, `odoo_list_connection_profiles`, `odoo_list_rights`,
`odoo_sdk_read`, `odoo_sdk_create`, `odoo_sdk_update`, `odoo_sdk_delete`,
`odoo_sdk_list_models`, `odoo_sdk_list_fields`, `odoo_sdk_list_allowed_models`,
`odoo_sdk_list_allowed_fields`. (The `docs_*` tools now come from
`docs-plugin` — same names, see its README.)

## Tests

`tests/` is a `pytest` suite (~200 tests, no real Odoo or Hermes install
needed — both are faked) covering `w_main`/`w_odoo` and the
integration layer (`tools.py`, `cli.py`, `__init__.py`). `test_rights_bridge.py`
exercises the cross-plugin bridge against the **real** `rights-plugin` code
(`models.create_access_right`, `engine.check_right`, ...) via the sibling
`sys.path` lookup described above — not a mock — so a regression in either
plugin's public contract (`rights_plugin_api`) fails this suite, not just
`rights-plugin`'s own:

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

Runs automatically in GitHub Actions on every push/PR (`../.github/workflows/ci.yml`). See
`tests/conftest.py` for how it loads the plugin package (mirroring Hermes's
own plugin loader) and fakes `hermes_constants`/Hermes's native `tools`
package, and `tests/pytest.ini` for why that file has to live in `tests/`
specifically (pytest tries to import `odoo_plugin/__init__.py` as an
ancestor package otherwise — see `.agents/DECISIONS.md`, 2026-08-06).

The suite caught a real bug in `w_main.data_manager.field.ListField`'s
lazy default (`OdooRight.fields`, or any `ListField`, left unset came back
`None` instead of `[]`) — fixed (one-line: the sentinel default was `None`
instead of `_MISSING`), see `.agents/DECISIONS.md` (2026-08-06) for the
root cause.

## Not ported (see `.agents/DECISIONS.md` for the reasoning)

- AI provider management (`sdk_providers/` in the OpenClaw version) — Hermes
  already has its own native multi-provider system.
- Rollback/snapshot/action-log — these were documented at length in the
  OpenClaw version's `AGENTS.md`/`README.md` but were never actually
  implemented there either; nothing to port.
