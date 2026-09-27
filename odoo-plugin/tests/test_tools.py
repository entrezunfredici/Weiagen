"""odoo_plugin/tools.py — tool schemas + handlers.

Loaded through the ``tools_mod`` fixture (see tests/conftest.py), which goes
through the real plugin-loading path. The module's own ``_ai``/``_config``
executor singletons are monkeypatched with lightweight fakes here so these
tests stay focused on the tool layer (schema shape, error wrapping, argument
plumbing) rather than re-testing the executors (see test_odoo_cli_for_ai.py /
test_odoo_cli_for_config.py for that).
"""

import json

import pytest

from w_main.errors_manager.errors import ConfirmationRequiredError, NotFoundError


class _FakeExecutor:
    """Records the last call and returns/raises whatever was configured."""

    def __init__(self):
        self.calls = []
        self._result = {"ok": True}
        self._raise = None

    def returning(self, result):
        self._result = result
        self._raise = None
        return self

    def raising(self, exc):
        self._raise = exc
        return self

    def execute(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self._raise is not None:
            raise self._raise
        return self._result


@pytest.fixture
def fake_ai(tools_mod, monkeypatch):
    fake = _FakeExecutor()
    monkeypatch.setattr(tools_mod, "_ai", fake)
    return fake


@pytest.fixture
def fake_config(tools_mod, monkeypatch):
    fake = _FakeExecutor()
    monkeypatch.setattr(tools_mod, "_config", fake)
    return fake


# ---------------------------------------------------------------------------
# _run — error-shape wrapping
# ---------------------------------------------------------------------------

def test_run_wraps_connector_error(tools_mod):
    def _boom():
        raise NotFoundError("nope", {"id": 1})

    result = json.loads(tools_mod._run(_boom))
    assert result == {"ok": False, "error": {"code": "NOT_FOUND", "message": "nope", "details": {"id": 1}}}


def test_run_wraps_generic_exception_as_unhandled(tools_mod):
    def _boom():
        raise RuntimeError("boom")

    result = json.loads(tools_mod._run(_boom))
    assert result["ok"] is False
    assert result["error"]["code"] == "UNHANDLED_ERROR"
    assert "boom" in result["error"]["message"]


def test_run_passes_through_successful_dict(tools_mod):
    result = json.loads(tools_mod._run(lambda: {"ok": True, "value": 42}))
    assert result == {"ok": True, "value": 42}


# ---------------------------------------------------------------------------
# Registration table sanity
# ---------------------------------------------------------------------------

def test_all_tools_have_unique_names(tools_mod):
    names = [entry[0] for entry in tools_mod.ALL_TOOLS]
    assert len(names) == len(set(names))


def test_all_tools_schema_name_matches_registration_name(tools_mod):
    for name, _toolset, schema, _handler, _emoji in tools_mod.ALL_TOOLS:
        assert schema["name"] == name


def test_confirmable_tools_are_a_subset_of_all_tools(tools_mod):
    all_names = {entry[0] for entry in tools_mod.ALL_TOOLS}
    assert tools_mod.CONFIRMABLE_TOOLS <= all_names


def test_odoo_sdk_crud_tools_are_confirmable(tools_mod):
    assert tools_mod.CONFIRMABLE_TOOLS == {
        "odoo_sdk_read", "odoo_sdk_create", "odoo_sdk_update", "odoo_sdk_delete",
    }


# ---------------------------------------------------------------------------
# Handlers — argument plumbing into _ai / _config
# ---------------------------------------------------------------------------

def test_handle_odoo_sdk_read_forwards_profile_and_fields(tools_mod, fake_ai):
    fake_ai.returning({"ok": True, "records": []})
    result = json.loads(tools_mod.handle_odoo_sdk_read(
        {"profile_id": "p1", "model": "res.partner", "fields": ["name"]},
    ))
    assert result["ok"] is True
    action, model, payload = fake_ai.calls[0][0]
    assert action == "odoo_read"
    assert model == "res.partner"
    assert payload["profile_id"] == "p1"
    assert payload["fields"] == ["name"]
    assert payload["confirmed"] is True  # tool layer always sets this — see _crud_payload docstring


def test_handle_odoo_sdk_read_omits_absent_optional_fields(tools_mod, fake_ai):
    fake_ai.returning({"ok": True})
    tools_mod.handle_odoo_sdk_read({"profile_id": "p1", "model": "res.partner"})
    _, _, payload = fake_ai.calls[0][0]
    assert "fields" not in payload
    assert "domain" not in payload
    assert "limit" not in payload


def test_handle_odoo_sdk_create_surfaces_confirmation_required(tools_mod, fake_ai):
    fake_ai.raising(ConfirmationRequiredError("needs confirmation", {"model": "res.partner"}))
    result = json.loads(tools_mod.handle_odoo_sdk_create(
        {"profile_id": "p1", "model": "res.partner", "values": {"name": "Acme"}},
    ))
    assert result["ok"] is False
    assert result["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_handle_odoo_sdk_update_forwards_id_and_ids(tools_mod, fake_ai):
    fake_ai.returning({"ok": True})
    tools_mod.handle_odoo_sdk_update({"profile_id": "p1", "model": "res.partner", "id": 5, "values": {}})
    _, _, payload = fake_ai.calls[0][0]
    assert payload["id"] == 5
    assert "ids" not in payload


def test_handle_odoo_sdk_delete(tools_mod, fake_ai):
    fake_ai.returning({"ok": True, "deleted_ids": [1]})
    result = json.loads(tools_mod.handle_odoo_sdk_delete({"profile_id": "p1", "model": "res.partner", "id": 1}))
    assert result["ok"] is True
    action = fake_ai.calls[0][0][0]
    assert action == "odoo_delete"


def test_handle_odoo_sdk_list_models(tools_mod, fake_ai):
    fake_ai.returning({"ok": True, "models": []})
    tools_mod.handle_odoo_sdk_list_models({"profile_id": "p1"})
    action, model, payload = fake_ai.calls[0][0]
    assert action == "odoo_list_models"
    assert payload == {"profile_id": "p1"}


def test_handle_odoo_config_validate_reports_missing_profiles_and_rights(tools_mod, fake_config):
    fake_config.execute = lambda action, payload: (
        {"profiles": []} if action == "list_profiles" else {"rights": []}
    )
    result = json.loads(tools_mod.handle_odoo_config_validate({}))
    assert result["ok"] is False
    assert "No connection profiles configured." in result["issues"]
    assert "No rights configured" in result["issues"][-1]


def test_handle_odoo_config_validate_ok_when_configured(tools_mod, fake_config):
    fake_config.execute = lambda action, payload: (
        {"profiles": [{"id": "p1", "label": "P1", "enabled": True}]} if action == "list_profiles"
        else {"rights": [{"id": "r1"}]}
    )
    result = json.loads(tools_mod.handle_odoo_config_validate({}))
    assert result["ok"] is True
    assert result["issues"] == []


def test_handle_odoo_list_connection_profiles_filters_disabled_by_default(tools_mod, fake_config):
    fake_config.returning({"profiles": [
        {"id": "p1", "enabled": True}, {"id": "p2", "enabled": False},
    ]})
    result = json.loads(tools_mod.handle_odoo_list_connection_profiles({}))
    assert [p["id"] for p in result["profiles"]] == ["p1"]


def test_handle_odoo_list_connection_profiles_include_disabled(tools_mod, fake_config):
    fake_config.returning({"profiles": [
        {"id": "p1", "enabled": True}, {"id": "p2", "enabled": False},
    ]})
    result = json.loads(tools_mod.handle_odoo_list_connection_profiles({"include_disabled": True}))
    assert {p["id"] for p in result["profiles"]} == {"p1", "p2"}


def test_handle_odoo_list_rights_filters_by_odoo_model(tools_mod, fake_config):
    fake_config.returning({"rights": [
        {"id": "r1", "odoo_model": "res.partner"}, {"id": "r2", "odoo_model": "project.task"},
    ]})
    result = json.loads(tools_mod.handle_odoo_list_rights({"odoo_model": "project.task"}))
    assert [r["id"] for r in result["rights"]] == ["r2"]
