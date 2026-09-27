"""Agent-facing tool schemas and handlers for the ``docs`` Hermes plugin.

Moved out of ``odoo-plugin/tools.py`` on 2026-09-24 (see
``.agents/DECISIONS.md``): document generation never depended on Odoo.
Tool **names** and argument shapes are unchanged, so skills and prompts
that used them keep working. Two additive changes:

- ``output_path`` is optional on the three ``docs_create_*`` tools, and
  confined to allowed directories (see ``docs_paths.py``);
- every successful create returns ``media`` (``"MEDIA:<path>"``): putting
  that tag in the final reply makes Hermes attach the file (Slack upload).

Handlers take ``(args, **kwargs)`` — Hermes dispatch passes ``task_id``/
``session_id``/.... Errors keep the
``{"ok": false, "error": {"code", "message", "details"}}`` shape the
odoo-plugin version produced (``VALIDATION_ERROR`` / ``UNHANDLED_ERROR``).
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from tools.registry import tool_result

from docs_paths import OutputPathError, media_tag, resolve_output_path
from w_docs.docx_generator import create_docx
from w_docs.docx_reader import read_docx
from w_docs.pptx_generator import create_pptx
from w_docs.pptx_reader import read_pptx
from w_docs.xlsx_generator import create_xlsx
from w_docs.xlsx_reader import read_xlsx

_DELIVERY_HINT = (
    "To send this file to the user, put the `media` value (MEDIA:<path>) on its own line in your "
    "final reply — Hermes then attaches the file. Do not paste the path alone."
)


class _MissingArgument(ValueError):
    pass


def _error(code: str, message: str) -> str:
    return tool_result({"ok": False, "error": {"code": code, "message": message, "details": {}}})


def _run(fn: Callable[[], dict]) -> str:
    """Call *fn* and map failures onto the documented error codes."""
    try:
        result = fn()
    except (OutputPathError, _MissingArgument) as exc:
        return _error("VALIDATION_ERROR", str(exc))
    except Exception as exc:  # noqa: BLE001 - same fallback as the odoo-plugin era
        return _error("UNHANDLED_ERROR", str(exc))
    return tool_result(result)


def _require(args: dict, key: str) -> Any:
    value = args.get(key)
    if value is None or value == "":
        raise _MissingArgument(f"missing required argument {key!r}")
    return value


def _create(generate: Callable[[str], dict], args: dict, *, extension: str, kind: str) -> dict:
    path = resolve_output_path(args.get("output_path"), extension=extension, kind=kind)
    result = generate(str(path))
    if result.get("ok"):
        result["media"] = media_tag(result.get("path") or path)
        result["delivery"] = _DELIVERY_HINT
    return result


_OUTPUT_PATH_PROPERTY = {
    "type": "string",
    "description": (
        "Optional. A file name (e.g. 'sales_2025.xlsx') or omit it entirely: the file is then written "
        "to Hermes's document cache, from where it can be attached to the reply. An absolute path is "
        "only accepted inside the configured output directories."
    ),
}

# ---------------------------------------------------------------------------
# Document generation tools — xlsx, docx, pptx
# ---------------------------------------------------------------------------

DOCS_CREATE_XLSX_SCHEMA: Dict[str, Any] = {
    "name": "docs_create_xlsx",
    "description": (
        "Create an Excel spreadsheet (.xlsx). Each sheet "
        "can have optional headers (styled in bold with a blue fill), data "
        "rows, optional auto-filter, and optional freeze of the top row. "
        "Column widths are auto-sized unless overridden per column letter. "
        "Returns `media` (MEDIA:<path>) to include in your reply to send the file."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "output_path": _OUTPUT_PATH_PROPERTY,
            "sheets": {
                "type": "array",
                "description": "List of sheets to create.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Sheet tab name (max 31 chars)."},
                        "headers": {"type": "array", "items": {"type": "string"}, "description": "Column header labels."},
                        "rows": {"type": "array", "items": {"type": "array", "items": {}}, "description": "Data rows — each row is an array of cell values."},
                        "freeze_top_row": {"type": "boolean", "description": "Freeze the header row (default false)."},
                        "auto_filter": {"type": "boolean", "description": "Enable auto-filter on header row (default false)."},
                        "column_widths": {"type": "object", "description": "Override column width by letter, e.g. {\"A\": 20}."},
                    },
                },
            },
        },
        "required": ["sheets"],
    },
}


def handle_docs_create_xlsx(args: dict, **kwargs) -> str:
    """Create an .xlsx file and return its path plus a ``MEDIA:`` tag."""
    return _run(lambda: _create(
        lambda path: create_xlsx(path, _require(args, "sheets")), args, extension=".xlsx", kind="spreadsheet"
    ))


DOCS_CREATE_DOCX_SCHEMA: Dict[str, Any] = {
    "name": "docs_create_docx",
    "description": (
        "Create a Word document (.docx). Content is a list "
        "of blocks: heading (level 1-4), paragraph, bullet_list, "
        "numbered_list, table, or page_break. An optional top-level title is "
        "rendered as a Heading 0 (document title style). "
        "Returns `media` (MEDIA:<path>) to include in your reply to send the file."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "output_path": _OUTPUT_PATH_PROPERTY,
            "title": {"type": "string", "description": "Document title rendered at the top (optional)."},
            "content": {
                "type": "array",
                "description": "Ordered list of content blocks.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "description": "'heading' | 'paragraph' | 'bullet_list' | 'numbered_list' | 'table' | 'page_break'"},
                        "level": {"type": "number", "description": "Heading level 1-4 (only for type='heading')."},
                        "text": {"type": "string", "description": "Text content (heading or paragraph)."},
                        "items": {"type": "array", "items": {"type": "string"}, "description": "List items (bullet_list or numbered_list)."},
                        "headers": {"type": "array", "items": {"type": "string"}, "description": "Table column headers (type='table')."},
                        "rows": {"type": "array", "items": {"type": "array", "items": {}}, "description": "Table data rows (type='table')."},
                    },
                },
            },
        },
        "required": ["content"],
    },
}


def handle_docs_create_docx(args: dict, **kwargs) -> str:
    """Create a .docx file and return its path plus a ``MEDIA:`` tag."""
    return _run(lambda: _create(
        lambda path: create_docx(path, _require(args, "content"), title=args.get("title")),
        args, extension=".docx", kind="document",
    ))


DOCS_CREATE_PPTX_SCHEMA: Dict[str, Any] = {
    "name": "docs_create_pptx",
    "description": (
        "Create a PowerPoint presentation (.pptx). Each "
        "slide has a layout: 'title' (title + subtitle), 'content' (title + "
        "bullet list), 'two_column' (title + left/right bullet lists), or "
        "'blank' (free text body). "
        "Returns `media` (MEDIA:<path>) to include in your reply to send the file."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "output_path": _OUTPUT_PATH_PROPERTY,
            "slides": {
                "type": "array",
                "description": "Ordered list of slides.",
                "items": {
                    "type": "object",
                    "properties": {
                        "layout": {"type": "string", "description": "'title' | 'content' | 'two_column' | 'blank'"},
                        "title": {"type": "string", "description": "Slide title (all layouts except blank)."},
                        "subtitle": {"type": "string", "description": "Subtitle text (layout='title' only)."},
                        "content": {"type": "array", "items": {"type": "string"}, "description": "Bullet points (layout='content')."},
                        "left": {"type": "array", "items": {"type": "string"}, "description": "Left column bullets (layout='two_column')."},
                        "right": {"type": "array", "items": {"type": "string"}, "description": "Right column bullets (layout='two_column')."},
                        "body": {"type": "string", "description": "Free-form text body (layout='blank')."},
                    },
                },
            },
        },
        "required": ["slides"],
    },
}


def handle_docs_create_pptx(args: dict, **kwargs) -> str:
    """Create a .pptx file and return its path plus a ``MEDIA:`` tag."""
    return _run(lambda: _create(
        lambda path: create_pptx(path, _require(args, "slides")), args, extension=".pptx", kind="presentation"
    ))


# ---------------------------------------------------------------------------
# Document reading tools — xlsx, docx, pptx (unchanged from odoo-plugin)
# ---------------------------------------------------------------------------

DOCS_READ_XLSX_SCHEMA: Dict[str, Any] = {
    "name": "docs_read_xlsx",
    "description": (
        "Read and extract the content of an Excel file (.xlsx). Returns "
        "every sheet with its headers and rows. Use sheet_names to limit to "
        "specific sheets."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "input_path": {"type": "string", "description": "Absolute path to the .xlsx file to read."},
            "sheet_names": {"type": "array", "items": {"type": "string"}, "description": "Sheet names to extract. If omitted, every sheet is returned."},
        },
        "required": ["input_path"],
    },
}


def handle_docs_read_xlsx(args: dict, **kwargs) -> str:
    """Return every (or the selected) sheet of an .xlsx file."""
    return _run(lambda: read_xlsx(_require(args, "input_path"), args.get("sheet_names")))


DOCS_READ_DOCX_SCHEMA: Dict[str, Any] = {
    "name": "docs_read_docx",
    "description": (
        "Read and extract the content of a Word document (.docx). Returns "
        "the title, paragraphs, headings, and tables in document order."
    ),
    "parameters": {
        "type": "object",
        "properties": {"input_path": {"type": "string", "description": "Absolute path to the .docx file to read."}},
        "required": ["input_path"],
    },
}


def handle_docs_read_docx(args: dict, **kwargs) -> str:
    """Return the title, headings, paragraphs and tables of a .docx file."""
    return _run(lambda: read_docx(_require(args, "input_path")))


DOCS_READ_PPTX_SCHEMA: Dict[str, Any] = {
    "name": "docs_read_pptx",
    "description": (
        "Read and extract the content of a PowerPoint presentation (.pptx). "
        "Returns, for each slide, its number, title, and all visible text."
    ),
    "parameters": {
        "type": "object",
        "properties": {"input_path": {"type": "string", "description": "Absolute path to the .pptx file to read."}},
        "required": ["input_path"],
    },
}


def handle_docs_read_pptx(args: dict, **kwargs) -> str:
    """Return the number, title and visible text of every slide of a .pptx file."""
    return _run(lambda: read_pptx(_require(args, "input_path")))


# (name, toolset, schema, handler, emoji) — same table shape and toolset
# name ("docs") as when these lived in odoo-plugin.
DOCS_TOOLS = (
    ("docs_create_xlsx", "docs", DOCS_CREATE_XLSX_SCHEMA, handle_docs_create_xlsx, "📊"),
    ("docs_create_docx", "docs", DOCS_CREATE_DOCX_SCHEMA, handle_docs_create_docx, "📄"),
    ("docs_create_pptx", "docs", DOCS_CREATE_PPTX_SCHEMA, handle_docs_create_pptx, "📽️"),
    ("docs_read_xlsx", "docs", DOCS_READ_XLSX_SCHEMA, handle_docs_read_xlsx, "📊"),
    ("docs_read_docx", "docs", DOCS_READ_DOCX_SCHEMA, handle_docs_read_docx, "📄"),
    ("docs_read_pptx", "docs", DOCS_READ_PPTX_SCHEMA, handle_docs_read_pptx, "📽️"),
)
