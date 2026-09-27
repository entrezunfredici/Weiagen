# weiagen_hermes

Self-hosted deployment of [Hermes Agent](https://github.com/NousResearch/hermes-agent)
(NousResearch), plus four custom plugins developed in this repo: `odoo`
(Odoo connector), `docs` (office document generation — xlsx/docx/pptx —
sent back to the user as an attachment, see
[`docs-plugin/README.md`](docs-plugin/README.md)), `rights` (generic
identity→role→resource deny-by-default authorization, which `odoo`
delegates all of its access control to — see
[`rights-plugin/README.md`](rights-plugin/README.md)) and `audit`
(hash-chained audit log of every tool call and approval decision — see
[`audit-plugin/README.md`](audit-plugin/README.md)).

This repo does **not** vendor Hermes Agent's source code — locally, it runs
the published `nousresearch/hermes-agent` Docker image and bind-mounts the
plugin/skills straight from this repo (`docker-compose.yml`, read-only). No
image rebuild, ever, for this path. See `.agents/DECISIONS.md` for the
reasoning (and for a real bug this session hit: a *symlink* into `~/.hermes`
pointing outside the mounted volume does not resolve inside the container —
direct bind mounts were used instead).

For a **remote server** that doesn't have this repo checked out on disk (so
no bind mount is possible), a custom image (`Dockerfile`) bakes the plugin,
skills, and their dependencies in instead (`docker-compose.server.yml`).

> There is no documented deployment procedure right now — the previous one
> (`.agents/DEPLOY.md`) was removed on 2026-09-27; a new deployment
> mechanism will be added later (see `.agents/DECISIONS.md`). The sections
> below assume a Hermes container is already running and cover enabling
> each plugin once it is.

## Layout

```text
docker-compose.yml         # local deploy: published image + bind-mounts of
                            # odoo-plugin/, rights-plugin/, skills-odoo/* and
                            # skills-rights/* (live edits, no rebuild)
docker-compose.server.yml  # remote deploy: custom image (built from Dockerfile), no bind mounts
Dockerfile                  # bakes odoo-plugin/ + rights-plugin/ + skills-odoo/* +
                            # skills-rights/* + deps into the image, used only for
                            # the remote/server path above
.env                        # deployment secrets (never committed)
.github/workflows/ci.yml     # CI: runs odoo-plugin/tests/ and rights-plugin/tests/ on every push/PR (see below)

odoo-plugin/          # Hermes plugin: Odoo connector
odoo-plugin/tests/    # pytest unit test suite for the plugin (see "Tests" below)
rights-plugin/        # Hermes plugin: generic identity→role→resource authorization,
                      # used by odoo-plugin and by Hermes's own tools/crons (see below)
rights-plugin/tests/  # pytest unit test suite for the plugin (see "Tests" below)
audit-plugin/         # Hermes plugin: append-only, hash-chained audit log of every
                      # tool call (incl. calls blocked by rights) + approval decisions
audit-plugin/tests/   # pytest unit test suite for the plugin (see "Tests" below)
docs-plugin/          # Hermes plugin: create/read xlsx, docx, pptx (moved out of odoo-plugin)
docs-plugin/tests/    # pytest unit test suite for the plugin (see "Tests" below)
skills-docs/          # skill installed alongside docs-plugin (tool usage + MEDIA delivery)
skills-odoo/          # skills installed alongside odoo-plugin (agent-facing usage docs)
skills-rights/        # skill installed alongside rights-plugin — how the agent should
                      # react to a blocked/approved tool call or cron job
skills/               # general-purpose Hermes skills, not Odoo-specific — portable
                       # backup only, not wired into any bind mount or Dockerfile COPY
searxng/settings.yml   # config for the self-hosted SearXNG service (web search backend)
```

## Web search backend (SearXNG)

Both compose files also start a `searxng` service (public `searxng/searxng`
image, no port published to the host — reachable only from `hermes` over the
internal compose network). Hermes' built-in web-search tool picks a provider
from a fallback chain (`exa → searxng → brave-free → ddgs`) based on which
API key is configured; with none set, it silently falls back to `ddgs`
(unauthenticated DuckDuckGo scraping), which gets rate-limited/blocked and
can lead the model to fabricate plausible-looking URLs when it comes back
empty. Setting `SEARXNG_URL` (already wired in both compose files) makes
Hermes prefer the self-hosted SearXNG instance instead — real aggregated
results, free, no API key, no request cap. See `.agents/CHANGELOG_AGENT.md`
(2026-08-05) for the full diagnosis.

`searxng/settings.yml` enables the JSON search format (off by default on the
stock image) and disables the request limiter — both are only safe because
the instance is never exposed outside the docker network. If you ever add a
paid provider (Brave/Tavily/Exa) later, just set its API key in `.env`; it
takes priority over `searxng` automatically per the fallback order above.

## Enable the `odoo` plugin

The plugin/skills are already inside the container via the bind mounts above
— Hermes still needs to (a) have the plugin's Python deps installed in its
own venv, and (b) have the plugin explicitly enabled (plugins are opt-in by
default). Both steps run **inside** the container, not on the host:

```bash
docker exec hermes uv pip install --python /opt/hermes/.venv/bin/python \
  -r /opt/data/plugins/odoo/requirements.txt

docker exec hermes /opt/hermes/.venv/bin/hermes plugins enable odoo
docker exec hermes /opt/hermes/.venv/bin/hermes plugins enable rights
docker restart hermes
```

> The `uv pip install` step does **not** persist across
> `docker compose up -d --force-recreate` or an image update — the venv lives
> in the container's own filesystem layer, not in the `~/.hermes` volume.
> Re-run it whenever the container is recreated. (Known limitation — see
> `.agents/DECISIONS.md`.)

**`odoo` has no authorization logic of its own anymore — it delegates
entirely to `rights` (see below)**; both must be enabled together, or every
`odoo_sdk_*` CRUD call fails closed. Then configure a connection profile
and at least one right:

```bash
docker exec hermes /opt/hermes/.venv/bin/hermes odoo profile add default \
  --base-url https://mycompany.odoo.com --database mycompany \
  --login api-bot --password '...'

docker exec hermes /opt/hermes/.venv/bin/hermes rights right add \
  --role everyone --resource-type odoo_model --resource-id "default:project.task" \
  --fields '*' --read --create --require-confirmation
```

See [`odoo-plugin/README.md`](odoo-plugin/README.md) for the full tool list,
the authorization model, and the confirmation flow.

## Enable the `rights` plugin

`rights-plugin/` is a generic, Odoo-agnostic deny-by-default authorization
plugin: identity (any platform Hermes talks to) → role bindings, and role →
resource access rights. It gates `odoo`'s tools (see above) and can gate any
Hermes built-in tool/cron or another plugin's tool by name, since Hermes's
`pre_tool_call` hook fires uniformly for all of them — see
[`rights-plugin/README.md`](rights-plugin/README.md) for the full model
(multi-role combination rule, resource/field wildcards, confirmation flow).

```bash
docker exec hermes /opt/hermes/.venv/bin/hermes plugins enable rights
docker restart hermes
```

No dependency-install step — this plugin is pure stdlib, nothing to `uv pip
install`. Bind an identity to a role and grant that role access to a
built-in tool:

```bash
docker exec hermes /opt/hermes/.venv/bin/hermes rights role bind \
  --platform slack --user U0123ABC --roles admin --label "Fred"

docker exec hermes /opt/hermes/.venv/bin/hermes rights right add \
  --role admin --resource-type hermes_tool --resource-id shell_exec --execute
```

A dashboard tab ("Access Groups", after "Odoo") gives the same management
surface as the CLI above, plus a generic view grouped by `resource_type` —
Hermes's own general access groups (`hermes_tool`, `hermes_cron`) alongside
any resource type a delegating plugin introduces (`odoo_model` today). See
[`rights-plugin/README.md`](rights-plugin/README.md#dashboard).

`rights-plugin` also signs a short-lived, opaque identity token per
**external** MCP microservice — never a Hermes plugin — injected into
context every turn so those services can verify the caller's roles on
their own side without trusting the LLM to relay them honestly. Each
external MCP gets its own signing key (`hermes rights mcp-key add`, or the
dashboard's "MCP signing keys" section — no `.env`/redeploy needed to
add/rotate one). This plugin never enforces anything inside an MCP server
itself; see
[`rights-plugin/README.md`](rights-plugin/README.md#mcp-identity-tokens-for-external-microservices-token_signerpy)
for the token format and the planned HMAC→EdDSA migration.

## Enable the `docs` plugin

`docs-plugin/` provides `docs_create_xlsx/docx/pptx` and
`docs_read_xlsx/docx/pptx` (moved out of `odoo` on 2026-09-24 — same tool
names). Generated files land in Hermes's document cache and each result
carries a `MEDIA:<path>` line the agent puts in its reply, which makes
Hermes attach the file (Slack upload). Writes outside that cache (and
`DOCS_OUTPUT_DIRS`) are refused.

```bash
docker exec hermes uv pip install --python /opt/hermes/.venv/bin/python \
  -r /opt/data/plugins/docs/requirements.txt
docker exec hermes /opt/hermes/.venv/bin/hermes plugins enable docs
docker restart hermes
```

See [`docs-plugin/README.md`](docs-plugin/README.md).

## Enable the `audit` plugin

`audit-plugin/` records every tool call — who (platform + user id, resolved
from the session), which tool, redacted arguments, outcome (`ok`, `error`,
`blocked` by `rights`, `cancelled`, `timeout`) — and every approval
decision, in a hash-chained SQLite log
(`$HERMES_HOME/audit-plugin-data/audit.db`). Tool results are never
stored, only their size. Independent of `rights` (keeps recording if it is
disabled), stdlib only.

```bash
docker exec hermes /opt/hermes/.venv/bin/hermes plugins enable audit
docker restart hermes

docker exec -u hermes hermes /opt/hermes/.venv/bin/hermes audit list --status blocked --since 24h
docker exec -u hermes hermes /opt/hermes/.venv/bin/hermes audit verify
```

Also available as a read-only "Audit" dashboard tab. Two optional `.env`
variables: `AUDIT_RETENTION_DAYS` (default 90, `0` = forever) and
`AUDIT_AGENT_TOOL_ENABLED` (registers the `audit_search` agent tool — off by
default because it exposes everyone's activity; restrict it with a
`rights` right first). See [`audit-plugin/README.md`](audit-plugin/README.md).

## Portable skills (`skills/`)

General-purpose Hermes skills that aren't tied to the `odoo` plugin live in
`skills/` — kept here just so they aren't lost, not deployed automatically
anywhere. To use one on a given Hermes instance, copy its folder into
`~/.hermes/skills/` on that host:

```bash
cp -r skills/mcp-tool-discovery ~/.hermes/skills/
cp -r skills/research-citations ~/.hermes/skills/research/
# or, on a remote server (docker-compose*.yml bind-mounts ${HOME}/.hermes
# on the host running the container to /opt/data):
scp -r skills/mcp-tool-discovery your-server:~/.hermes/skills/
scp -r skills/research-citations your-server:~/.hermes/skills/research/
```

Currently portable: `mcp-tool-discovery` (never author a procedural skill
for an MCP connector's tools — trust the live tool catalog instead) and
`research-citations` (no synthetic `【N†Lstart-Lend】`-style citation
markers — Hermes doesn't render them; fall back to the `browser` toolset
when `web_extract` fails instead of citing an unread search snippet as if
it were a verified source).

## Tests & CI

`odoo-plugin/`, `rights-plugin/`, `audit-plugin/` and `docs-plugin/` each have
their own `pytest` unit test suite (`*/tests/`, ~180, ~170, ~90 and ~40 tests
respectively) — no real Odoo instance
or Hermes container needed; Odoo itself and Hermes's native `tools`/
`hermes_state` modules are faked. `odoo-plugin/tests/` covers the
right/secret/CRUD engine (`w_main`, `w_odoo`) and the plugin integration
layer (`tools.py`, `cli.py`, `__init__.py`'s `pre_tool_call` hook and
`register()`), including `test_rights_bridge.py` which exercises the real
`rights-plugin` code across the sibling `sys.path` lookup, not a mock.
`rights-plugin/tests/` covers its vendored `rights_w_main`, models,
decision engine, identity resolution, hooks, CLI, and public
`rights_plugin_api` surface. `audit-plugin/tests/` covers the SQLite store
(hash chain, tampering detection, retention/purge, concurrent writes),
argument redaction, both hooks, the CLI and the `audit_search` tool.
`docs-plugin/tests/` covers the generators/readers (real files, round-trip),
the output-path policy (default dir, allowed roots, `..`/symlink escapes,
extension) and the tool handlers.
Deployment (`docker-compose*.yml`) has no
automated tests, still verified manually per `.agents/AGENT.md`.

```bash
cd odoo-plugin      # or rights-plugin, audit-plugin, docs-plugin
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

`.github/workflows/ci.yml` runs the same command for all four plugins on every
push/pull request (GitHub Actions, no image build/push involved — deployment
stays manual). This repo moved from GitLab to GitHub on 2026-09-27; the same
jobs used to live in `.gitlab-ci.yml` (see `.agents/DECISIONS.md`). See each
plugin's `tests/conftest.py` and
`tests/pytest.ini` for how the test suite loads the plugin without a real
Hermes install, and `.agents/DECISIONS.md` (2026-08-06) for a pytest
collection gotcha hit while setting this up.

## CD & Kubernetes (prepared, not active yet)

`.github/workflows/cd.yml` builds and pushes the Docker image
(`DOCKERHUB_USERNAME`/`DOCKERHUB_PASSWORD` secrets required) whenever CI
passes on `dev`/`staging`/`main`, tags releases on `staging`/`main`, and can
deploy to Kubernetes (`k8s/preprod/`, `k8s/prod/` — a single Hermes
Deployment with a PVC, plus an internal SearXNG Deployment, no Postgres/
Redis) via `kubectl apply` + `rollout restart`. **Kubernetes deployment is
off by default** — set the GitHub Actions variables `K8S_PREPROD_ENABLED`/
`K8S_PROD_ENABLED` to `true` once a real cluster exists. See
`k8s/secrets.env.example` for the Secret to create by hand on the cluster,
and `.agents/DECISIONS.md` (2026-09-27) for why this is a minimal
`kubectl apply` setup rather than a Helm chart. Ingress hostnames are still
placeholders (`<votre-domaine.com>`) — replace them before applying.

## Documentation for AI coding assistants

See `.agents/` (`AGENT.md`, `CONVENTIONS.md`, `DECISIONS.md`,
`CHANGELOG_AGENT.md`) — read via `CLAUDE.md`.
