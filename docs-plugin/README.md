# `docs` — Hermes plugin

Create and read office documents — Excel (`.xlsx`), Word (`.docx`),
PowerPoint (`.pptx`) — and **send them to the user** as an attachment
(Slack upload included).

Split out of `odoo-plugin` on 2026-09-24: document generation never
depended on Odoo. `w_docs/` is the same OpenClaw-era code, moved as-is;
tool names and argument shapes are unchanged.

## Tools (toolset `docs`)

| Tool | Does |
| --- | --- |
| `docs_create_xlsx` | Sheets with headers (bold, blue fill), rows, optional freeze/auto-filter/column widths |
| `docs_create_docx` | Title + blocks: heading, paragraph, bullet/numbered list, table, page break |
| `docs_create_pptx` | Slides: `title`, `content`, `two_column`, `blank` layouts |
| `docs_read_xlsx` / `docs_read_docx` / `docs_read_pptx` | Extract content from an existing file (`input_path`) |

Full argument reference, with examples: the `docs-generator` skill
([`../skills-docs/docs/SKILL.md`](../skills-docs/docs/SKILL.md)).

## Getting the file to the user

Hermes's gateway turns a `MEDIA:<absolute path>` line in the agent's final
reply into a native attachment. Every successful `docs_create_*` call
returns it ready-made:

```json
{"ok": true, "path": "/opt/data/cache/documents/generated/ventes_2025.xlsx",
 "media": "MEDIA:/opt/data/cache/documents/generated/ventes_2025.xlsx",
 "delivery": "To send this file to the user, put the `media` value ..."}
```

The skill tells the agent to end its reply with that line; Hermes strips it
from the visible text and uploads the file.

## Where files are written

`output_path` is optional:

| `output_path` | Result |
| --- | --- |
| omitted / empty | `<HERMES_HOME>/cache/documents/generated/<kind>-<UTC timestamp>-<random>.<ext>` |
| `"ventes_2025.xlsx"` or `"q3/bilan"` | same directory (sub-directories kept, extension added if missing) |
| absolute path | accepted **only** inside an allowed directory |

Allowed directories: the default one above, plus any absolute path listed in
`DOCS_OUTPUT_DIRS` (comma-separated). Anything else — including the old
skill examples' `/workspace/...` — returns `VALIDATION_ERROR`. `..` and
symlinks pointing outside are rejected, and a different extension than the
tool's is refused (a call can never produce `config.yaml`).

Why the default directory: it is one of the roots Hermes **always** accepts
for `MEDIA:` delivery, even with `HERMES_MEDIA_DELIVERY_STRICT=1`. A file
written under an extra `DOCS_OUTPUT_DIRS` root only attaches in non-strict
mode (the default) or if that root is also in `HERMES_MEDIA_ALLOW_DIRS`.

Reading (`input_path`) is not restricted: the readers only parse office
files, and files users send on Slack land in Hermes's document cache.

Errors: `{"ok": false, "error": {"code": "VALIDATION_ERROR" | "UNHANDLED_ERROR", "message", "details"}}`.

## Enable

Dependencies (`openpyxl`, `python-docx`, `python-pptx`) are baked into the
server image. For the local bind-mount deployment, install them in the
container's venv (not persistent across a container recreate — same known
limitation as `odoo-plugin`):

```bash
docker exec hermes uv pip install --python /opt/hermes/.venv/bin/python \
  -r /opt/data/plugins/docs/requirements.txt
docker exec hermes /opt/hermes/.venv/bin/hermes plugins enable docs
docker restart hermes
```

Upgrading from a deployment where these tools came from `odoo`: enabling
`docs` is required, otherwise the `docs_*` tools disappear. Also do a
one-off cleanup of the old `odoo-docs` skill copy left on disk by any
existing deployment (`skills_sync` doesn't remove it on its own).

## Layout

```text
docs-plugin/
├── plugin.yaml
├── __init__.py       # register(): the six docs_* tools
├── tools.py          # schemas + handlers (MEDIA tag, error mapping)
├── docs_paths.py     # output-path policy (default dir, allowed roots, extension)
├── w_docs/         # xlsx/docx/pptx generators and readers (moved from odoo-plugin, unchanged)
└── tests/            # pytest suite
```

## Tests

```bash
cd docs-plugin
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```
