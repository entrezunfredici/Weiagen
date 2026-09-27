"""Agent-facing tool schemas and handlers for the ``odoo`` Hermes plugin.

Ported from the OpenClaw version of this plugin (``sdk-plugin/src/index.ts`` +
``w_odoo/cli.py`` + ``w_odoo/cli_config.py``). The
original design spawned a Python subprocess per tool call and exchanged JSON
over stdin/stdout — that indirection only existed because OpenClaw is a
Node.js host. Hermes is Python-core, so every handler here calls straight
into :mod:`w_odoo` in-process. (Document tools and :mod:`w_docs` now
live in ``docs-plugin/``.)

Handlers receive an ``args: dict`` positional argument plus ``**kwargs``
(Hermes's ``tools.registry`` dispatch convention calls every handler as
``entry.handler(args, **kwargs)`` — see ``tools/registry.py::dispatch`` —
forwarding ``task_id``/``session_id``/etc.; a handler missing ``**kwargs``
raises ``TypeError: unexpected keyword argument 'task_id'`` at call time)
and return a JSON string. Errors keep the exact wire shape the ``skills/``
docs already document (``{"ok": false, "error": {"code", "message",
"details"}}``, from :class:`w_main.errors_manager.errors.ConnectorError`)
rather than switching to Hermes's generic ``tool_error()`` shape, so the
ported skill docs stay accurate without a rewrite.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from tools.registry import tool_result

from w_main.errors_manager.errors import ConnectorError
from w_odoo import rights_bridge
from w_odoo.odoo_cli_for_ai import OdooAIExecutor
from w_odoo.odoo_cli_for_config import OdooConfigExecutor

_ai = OdooAIExecutor()
_config = OdooConfigExecutor()


def _roles_from_kwargs(kwargs: dict) -> list[str]:
    """Resolve the calling identity's roles from the session_id Hermes's
    dispatch passes to every handler (see module docstring) — via
    rights_bridge, which falls back to a degraded zero-roles identity if
    rights-plugin is unavailable (fail closed, never fail open)."""
    return rights_bridge.get_identity(kwargs.get("session_id")).roles


def _run(fn: Callable[[], dict]) -> str:
    """Call *fn*, converting a :class:`ConnectorError` (or any other
    exception) into the same ``{"ok": false, "error": {...}}`` shape the
    OpenClaw-era CLI wrappers produced — preserves the error-code contract
    ``skills/odoo/sdk/SKILL.md`` documents (``AUTHORIZATION_DENIED``,
    ``CONFIRMATION_REQUIRED``, ``VALIDATION_ERROR``, ``NOT_FOUND``,
    ``SERVICE_ERROR``, ``UNHANDLED_ERROR``).
    """
    try:
        result = fn()
    except ConnectorError as exc:
        return tool_result(exc.to_dict())
    except Exception as exc:  # noqa: BLE001 - mirrors the old cli.py fallback
        return tool_result({
            "ok": False,
            "error": {"code": "UNHANDLED_ERROR", "message": str(exc), "details": {}},
        })
    return tool_result(result)


# ---------------------------------------------------------------------------
# Config / diagnostic tools
# ---------------------------------------------------------------------------

ODOO_CONFIG_VALIDATE_SCHEMA: Dict[str, Any] = {
    "name": "odoo_config_validate",
    "description": (
        "Validate the SDK Odoo setup: check that at least one connection "
        "profile exists and is enabled, and that rights are configured so "
        "the AI can actually access Odoo."
    ),
    "parameters": {"type": "object", "properties": {}},
}


def handle_odoo_config_validate(args: dict, **kwargs) -> str:
    def _call() -> dict:
        profiles_result = _config.execute("list_profiles", {})
        rights_result = _config.execute("list_rights", {})

        profiles = profiles_result.get("profiles", [])
        rights = rights_result.get("rights", [])
        issues: list[str] = []
        if not profiles:
            issues.append("No connection profiles configured.")
        disabled = [p for p in profiles if not p.get("enabled")]
        if disabled:
            issues.append(
                f"{len(disabled)} profile(s) disabled: "
                f"{', '.join(p['id'] for p in disabled)}"
            )
        if not rights:
            issues.append("No rights configured — the AI cannot access Odoo without at least one right.")

        return {
            "ok": not issues,
            "profiles_count": len(profiles),
            "rights_count": len(rights),
            "profiles": [{"id": p["id"], "label": p["label"], "enabled": p["enabled"]} for p in profiles],
            "issues": issues,
        }

    return _run(_call)


ODOO_LIST_CONNECTION_PROFILES_SCHEMA: Dict[str, Any] = {
    "name": "odoo_list_connection_profiles",
    "description": "List Odoo connection profiles stored in the SDK system (no secrets exposed).",
    "parameters": {
        "type": "object",
        "properties": {
            "include_disabled": {
                "type": "boolean",
                "description": "Include disabled profiles. Defaults to false.",
            },
        },
    },
}


def handle_odoo_list_connection_profiles(args: dict, **kwargs) -> str:
    def _call() -> dict:
        result = _config.execute("list_profiles", {})
        profiles = result["profiles"]
        if not args.get("include_disabled"):
            profiles = [p for p in profiles if p.get("enabled")]
        return {"ok": True, "profiles": profiles, "count": len(profiles)}

    return _run(_call)


ODOO_LIST_RIGHTS_SCHEMA: Dict[str, Any] = {
    "name": "odoo_list_rights",
    "description": (
        "List rights configured in the SDK system. Each right defines which "
        "CRUD operations the AI may perform on a given profile, model, and "
        "set of fields."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "profile_id": {"type": "string", "description": "Filter by connection profile id."},
            "odoo_model": {"type": "string", "description": "Filter by Odoo model name."},
        },
    },
}


def handle_odoo_list_rights(args: dict, **kwargs) -> str:
    def _call() -> dict:
        result = _config.execute("list_rights", {"profile_id": args.get("profile_id") or ""})
        rights = result["rights"]
        odoo_model = args.get("odoo_model")
        if odoo_model:
            rights = [r for r in rights if r.get("odoo_model") == odoo_model]
        return {"ok": True, "rights": rights, "count": len(rights)}

    return _run(_call)


# ---------------------------------------------------------------------------
# SDK Odoo tools — profile-based rights (w_odoo stack)
# ---------------------------------------------------------------------------

def _crud_payload(args: dict, *extra_keys: str) -> dict:
    """Build the executor payload, forwarding only keys the caller actually set.

    Mirrors the old ``pythonBridge`` behaviour: absent optional fields (e.g.
    ``id``/``ids``) must stay absent from the payload rather than becoming
    ``None``, since ``odoo_cli_for_ai._update``/``_delete`` branch on
    ``"id" in payload``.

    ``confirmed`` is always ``True`` here, not model-supplied: the plugin's
    ``pre_tool_call`` hook (see ``__init__.py::_pre_tool_call``) is what
    decides whether THIS call needs a human's approval, and Hermes's own
    dispatch layer blocks the handler from ever running until that approval
    is granted (or fails closed on denial/timeout) — reaching this code at
    all means either no confirmation was required, or a human already
    approved it through that gate. Passing the model's own ``confirmed``
    flag through unchanged would make the executor's internal
    ``ConfirmationRequiredError`` check fire a second time even after a real
    human approval, since the model has no way to know that approval
    happened out-of-band — that was a real bug caught by re-checking this
    against the ``skills-odoo/odoo-sdk`` skill doc.
    """
    payload: dict[str, Any] = {"profile_id": args["profile_id"], "confirmed": True}
    for key in extra_keys:
        if key in args and args[key] is not None:
            payload[key] = args[key]
    return payload


ODOO_SDK_READ_SCHEMA: Dict[str, Any] = {
    "name": "odoo_sdk_read",
    "description": (
        "Read records from an Odoo model using the SDK rights system. Access "
        "is gated per field by rights linked to the profile. Only fields "
        "explicitly allowed by a matching OdooRight are returned."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "profile_id": {"type": "string", "description": "Connection profile id configured in w_odoo."},
            "model": {"type": "string", "description": "Odoo model name, e.g. 'project.task'."},
            "fields": {"type": "array", "items": {"type": "string"}, "description": "Fields to read. Defaults to ['id', 'name']."},
            "domain": {"type": "array", "items": {}, "description": "Odoo domain filter, e.g. [['project_id', '=', 1]]."},
            "limit": {"type": "number", "description": "Max records to return. Defaults to 25."},
        },
        "required": ["profile_id", "model"],
    },
}


def handle_odoo_sdk_read(args: dict, **kwargs) -> str:
    payload = _crud_payload(args, "fields", "domain", "limit")
    roles = _roles_from_kwargs(kwargs)
    return _run(lambda: _ai.execute("odoo_read", args["model"], payload, roles=roles))


ODOO_SDK_CREATE_SCHEMA: Dict[str, Any] = {
    "name": "odoo_sdk_create",
    "description": (
        "Create a record in an Odoo model using the SDK rights system. Each "
        "field is checked individually; unauthorized fields are silently "
        "dropped. If the matching right requires confirmation, Hermes will "
        "pause and prompt the user to approve before this actually runs — "
        "no retry needed on your part.\n\n"
        "Rich-text fields (type 'html', e.g. project.task.description, "
        "mail.message.body): write plain text with '\\n' for line breaks — "
        "it is auto-converted to <p>/<br/> so line breaks always render "
        "(Odoo does not interpret raw '\\n' itself). To style content beyond "
        "line breaks, write real HTML tags directly instead of markdown: "
        "<b>/<strong> bold, <i>/<em> italic, <ul><li>/<ol><li> lists, "
        "<h2>/<h3> headings, <a href=\"...\"> links. Any value containing "
        "HTML tags is passed through as-is (not escaped), so mixing '\\n' "
        "and tags in the same value works as long as the tags are valid."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "profile_id": {"type": "string", "description": "Connection profile id."},
            "model": {"type": "string", "description": "Odoo model name."},
            "values": {"type": "object", "description": "Field values for the new record."},
        },
        "required": ["profile_id", "model", "values"],
    },
}


def handle_odoo_sdk_create(args: dict, **kwargs) -> str:
    payload = _crud_payload(args, "values")
    roles = _roles_from_kwargs(kwargs)
    return _run(lambda: _ai.execute("odoo_create", args["model"], payload, roles=roles))


ODOO_SDK_UPDATE_SCHEMA: Dict[str, Any] = {
    "name": "odoo_sdk_update",
    "description": (
        "Update one or more records in an Odoo model using the SDK rights "
        "system. Authorization is evaluated per field. Unauthorized fields "
        "are silently dropped.\n\n"
        "Rich-text fields (type 'html'): same rule as odoo_sdk_create — "
        "'\\n' for line breaks (auto-converted to <p>/<br/>), real HTML tags "
        "(<b>, <ul><li>, <h2>, <a href=...>) to style content."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "profile_id": {"type": "string", "description": "Connection profile id."},
            "model": {"type": "string", "description": "Odoo model name."},
            "id": {"type": "number", "description": "Single record id to update."},
            "ids": {"type": "array", "items": {"type": "number"}, "description": "Multiple record ids to update."},
            "values": {"type": "object", "description": "Fields to update."},
        },
        "required": ["profile_id", "model", "values"],
    },
}


def handle_odoo_sdk_update(args: dict, **kwargs) -> str:
    payload = _crud_payload(args, "id", "ids", "values")
    roles = _roles_from_kwargs(kwargs)
    return _run(lambda: _ai.execute("odoo_update", args["model"], payload, roles=roles))


ODOO_SDK_DELETE_SCHEMA: Dict[str, Any] = {
    "name": "odoo_sdk_delete",
    "description": (
        "Delete one or more records in an Odoo model using the SDK rights "
        "system. Requires an OdooRight with delete=true and fields=['*'] "
        "for the profile/model. If confirmation is required, Hermes will "
        "pause and prompt the user to approve before this actually runs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "profile_id": {"type": "string", "description": "Connection profile id."},
            "model": {"type": "string", "description": "Odoo model name."},
            "id": {"type": "number", "description": "Single record id to delete."},
            "ids": {"type": "array", "items": {"type": "number"}, "description": "Multiple record ids to delete."},
        },
        "required": ["profile_id", "model"],
    },
}


def handle_odoo_sdk_delete(args: dict, **kwargs) -> str:
    payload = _crud_payload(args, "id", "ids")
    roles = _roles_from_kwargs(kwargs)
    return _run(lambda: _ai.execute("odoo_delete", args["model"], payload, roles=roles))


ODOO_SDK_LIST_MODELS_SCHEMA: Dict[str, Any] = {
    "name": "odoo_sdk_list_models",
    "description": "List available Odoo models for a given connection profile.",
    "parameters": {
        "type": "object",
        "properties": {"profile_id": {"type": "string", "description": "Connection profile id."}},
        "required": ["profile_id"],
    },
}


def handle_odoo_sdk_list_models(args: dict, **kwargs) -> str:
    return _run(lambda: _ai.execute("odoo_list_models", "", {"profile_id": args["profile_id"]}))


ODOO_SDK_LIST_FIELDS_SCHEMA: Dict[str, Any] = {
    "name": "odoo_sdk_list_fields",
    "description": (
        "List fields of an Odoo model (schema introspection). Use to "
        "discover what fields exist before reading or writing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "profile_id": {"type": "string", "description": "Connection profile id."},
            "model": {"type": "string", "description": "Odoo model name."},
        },
        "required": ["profile_id", "model"],
    },
}


def handle_odoo_sdk_list_fields(args: dict, **kwargs) -> str:
    return _run(lambda: _ai.execute("odoo_list_fields", args["model"], {"profile_id": args["profile_id"]}))


ODOO_SDK_LIST_ALLOWED_MODELS_SCHEMA: Dict[str, Any] = {
    "name": "odoo_sdk_list_allowed_models",
    "description": (
        "List only the Odoo models the AI is authorized to access for a "
        "given profile, based on the configured rights. Faster than "
        "odoo_sdk_list_models (no Odoo connection needed) and scoped to "
        "what the AI can actually use. Returns CRUD flags per model."
    ),
    "parameters": {
        "type": "object",
        "properties": {"profile_id": {"type": "string", "description": "Connection profile id."}},
        "required": ["profile_id"],
    },
}


def handle_odoo_sdk_list_allowed_models(args: dict, **kwargs) -> str:
    roles = _roles_from_kwargs(kwargs)
    return _run(lambda: _ai.execute(
        "odoo_list_allowed_models", "", {"profile_id": args["profile_id"]}, roles=roles
    ))


ODOO_SDK_LIST_ALLOWED_FIELDS_SCHEMA: Dict[str, Any] = {
    "name": "odoo_sdk_list_allowed_fields",
    "description": (
        "List only the fields of an Odoo model that the AI is authorized to "
        "access for a given profile, based on the configured rights. Returns "
        "field metadata (type, label, required, readonly) and CRUD flags "
        "per field. Use this instead of odoo_sdk_list_fields to avoid "
        "requesting unauthorized fields."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "profile_id": {"type": "string", "description": "Connection profile id."},
            "model": {"type": "string", "description": "Odoo model name, e.g. 'res.partner'."},
        },
        "required": ["profile_id", "model"],
    },
}


def handle_odoo_sdk_list_allowed_fields(args: dict, **kwargs) -> str:
    roles = _roles_from_kwargs(kwargs)
    return _run(lambda: _ai.execute(
        "odoo_list_allowed_fields", args["model"], {"profile_id": args["profile_id"]}, roles=roles
    ))


# ---------------------------------------------------------------------------
# Registration table — consumed by odoo_plugin/__init__.py::register()
# ---------------------------------------------------------------------------
# (name, toolset, schema, handler, emoji)

ODOO_TOOLS = (
    ("odoo_config_validate", "odoo", ODOO_CONFIG_VALIDATE_SCHEMA, handle_odoo_config_validate, "🩺"),
    ("odoo_list_connection_profiles", "odoo", ODOO_LIST_CONNECTION_PROFILES_SCHEMA, handle_odoo_list_connection_profiles, "🔗"),
    ("odoo_list_rights", "odoo", ODOO_LIST_RIGHTS_SCHEMA, handle_odoo_list_rights, "🛂"),
    ("odoo_sdk_read", "odoo", ODOO_SDK_READ_SCHEMA, handle_odoo_sdk_read, "📖"),
    ("odoo_sdk_create", "odoo", ODOO_SDK_CREATE_SCHEMA, handle_odoo_sdk_create, "🆕"),
    ("odoo_sdk_update", "odoo", ODOO_SDK_UPDATE_SCHEMA, handle_odoo_sdk_update, "✏️"),
    ("odoo_sdk_delete", "odoo", ODOO_SDK_DELETE_SCHEMA, handle_odoo_sdk_delete, "🗑️"),
    ("odoo_sdk_list_models", "odoo", ODOO_SDK_LIST_MODELS_SCHEMA, handle_odoo_sdk_list_models, "📚"),
    ("odoo_sdk_list_fields", "odoo", ODOO_SDK_LIST_FIELDS_SCHEMA, handle_odoo_sdk_list_fields, "🔎"),
    ("odoo_sdk_list_allowed_models", "odoo", ODOO_SDK_LIST_ALLOWED_MODELS_SCHEMA, handle_odoo_sdk_list_allowed_models, "✅"),
    ("odoo_sdk_list_allowed_fields", "odoo", ODOO_SDK_LIST_ALLOWED_FIELDS_SCHEMA, handle_odoo_sdk_list_allowed_fields, "✅"),
)

# The docs_* tools (xlsx/docx/pptx) moved to docs-plugin on 2026-09-24 —
# see .agents/DECISIONS.md. Same names and toolset, different plugin.
ALL_TOOLS = ODOO_TOOLS

# Tool names whose OdooRight can carry require_confirmation=true — checked by
# the plugin's pre_tool_call hook (see odoo_plugin/__init__.py) so Hermes's
# native human-approval gate runs BEFORE the handler executes, instead of the
# old OpenClaw design's bespoke 90s REST poll (requestUiConfirmation).
CONFIRMABLE_TOOLS = {"odoo_sdk_read", "odoo_sdk_create", "odoo_sdk_update", "odoo_sdk_delete"}
