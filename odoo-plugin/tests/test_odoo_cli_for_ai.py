"""w_odoo.odoo_cli_for_ai.OdooAIExecutor — right-checked CRUD against Odoo.

OdooClient itself (real network/odoolib) is monkeypatched out; FakeOdooClient
(tests/conftest.py) stands in. Rights now come from rights-plugin (see
w_odoo/rights_bridge.py) — ``_right()`` below is a thin test helper that
creates an AccessRight bound to role "everyone" (resource_id =
f"{profile_id}:{odoo_model}"), and every executor.execute() call passes
``roles=["everyone"]`` explicitly, mirroring what tools.py/__init__.py
resolve from the caller's identity in real usage.
"""

import pytest

import w_odoo.odoo_cli_for_ai as odoo_cli_for_ai
from w_main.errors_manager.errors import (
    AuthorizationError,
    ConfirmationRequiredError,
    NotFoundError,
    ValidationError,
)
from w_odoo.odoo_cli_for_ai import OdooAIExecutor
from w_odoo.odoo_profile import create_odoo_profile
from tests.conftest import FakeOdooClient


def _right(profile_id: str, odoo_model: str, fields: list[str], **kwargs):
    import models
    return models.create_access_right(
        roles=["everyone"], resource_type="odoo_model",
        resource_id=f"{profile_id}:{odoo_model}", fields=fields, **kwargs,
    )


@pytest.fixture(autouse=True)
def _patch_odoo_client(monkeypatch):
    """Replace the real OdooClient with FakeOdooClient for every test here."""
    monkeypatch.setattr(odoo_cli_for_ai, "OdooClient", FakeOdooClient)


@pytest.fixture
def executor():
    return OdooAIExecutor()


@pytest.fixture
def profile():
    return create_odoo_profile(
        id="p1", label="P1", base_url="https://odoo.example.com",
        database="db", login="ai@example.com", password="s3cret",
    )


def test_execute_requires_profile_id(executor):
    with pytest.raises(ValidationError):
        executor.execute("odoo_read", "res.partner", {}, roles=["everyone"])


def test_execute_unknown_profile_raises_not_found(executor):
    with pytest.raises(NotFoundError):
        executor.execute("odoo_read", "res.partner", {"profile_id": "missing"}, roles=["everyone"])


def test_execute_disabled_profile_raises_authorization_error(executor):
    create_odoo_profile(
        id="p1", label="P1", base_url="https://x", database="db", login="l", password="pw",
        enabled=False,
    )
    with pytest.raises(AuthorizationError):
        executor.execute("odoo_read", "res.partner", {"profile_id": "p1"}, roles=["everyone"])


def test_execute_without_roles_falls_back_with_a_warning(executor, profile):
    # roles=None should still work (fallback to [ROLE_EVERYONE]) — every
    # real call site passes roles explicitly, but the fallback must not
    # crash if one ever forgets to.
    with pytest.raises(AuthorizationError):
        executor.execute("odoo_read", "res.partner", {"profile_id": "p1", "fields": ["name"]})


def test_read_denies_by_default_no_right_configured(executor, profile):
    with pytest.raises(AuthorizationError):
        executor.execute(
            "odoo_read", "res.partner", {"profile_id": "p1", "fields": ["name"]}, roles=["everyone"],
        )


def test_read_allowed_field_returns_records(executor, profile):
    _right("p1", "res.partner", ["name"], read=True)
    result = executor.execute(
        "odoo_read", "res.partner", {"profile_id": "p1", "fields": ["name"]}, roles=["everyone"],
    )
    assert result["ok"] is True
    assert result["allowed_fields"] == ["name"]
    assert result["denied_fields"] == []


def test_read_partially_denied_fields_reported_separately(executor, profile):
    _right("p1", "res.partner", ["name"], read=True)
    result = executor.execute(
        "odoo_read", "res.partner", {"profile_id": "p1", "fields": ["name", "secret_field"]},
        roles=["everyone"],
    )
    assert result["allowed_fields"] == ["name"]
    assert result["denied_fields"] == ["secret_field"]


def test_read_requires_confirmation_when_right_says_so(executor, profile):
    _right("p1", "res.partner", ["name"], read=True, confirm_read=True)
    with pytest.raises(ConfirmationRequiredError):
        executor.execute(
            "odoo_read", "res.partner", {"profile_id": "p1", "fields": ["name"]}, roles=["everyone"],
        )
    result = executor.execute(
        "odoo_read", "res.partner", {"profile_id": "p1", "fields": ["name"], "confirmed": True},
        roles=["everyone"],
    )
    assert result["ok"] is True


def test_create_denies_unauthorized_fields_and_keeps_authorized_ones(executor, profile):
    _right("p1", "res.partner", ["name"], create=True)
    result = executor.execute(
        "odoo_create", "res.partner",
        {"profile_id": "p1", "values": {"name": "Acme", "vat": "FR123"}},
        roles=["everyone"],
    )
    assert result["ok"] is True
    assert result["allowed_fields"] == ["name"]
    assert result["denied_fields"] == ["vat"]


def test_create_raises_when_no_field_allowed(executor, profile):
    _right("p1", "res.partner", ["name"], create=False)
    with pytest.raises(AuthorizationError):
        executor.execute(
            "odoo_create", "res.partner", {"profile_id": "p1", "values": {"name": "Acme"}},
            roles=["everyone"],
        )


def test_create_requires_confirmation(executor, profile):
    _right("p1", "res.partner", ["*"], create=True, confirm_create=True)
    with pytest.raises(ConfirmationRequiredError):
        executor.execute(
            "odoo_create", "res.partner", {"profile_id": "p1", "values": {"name": "Acme"}},
            roles=["everyone"],
        )


def test_update_requires_id_or_ids(executor, profile):
    _right("p1", "res.partner", ["*"], update=True)
    with pytest.raises(ValidationError):
        executor.execute(
            "odoo_update", "res.partner", {"profile_id": "p1", "values": {"name": "New"}},
            roles=["everyone"],
        )


def test_update_success_with_id(executor, profile):
    _right("p1", "res.partner", ["*"], update=True)
    result = executor.execute(
        "odoo_update", "res.partner", {"profile_id": "p1", "id": 42, "values": {"name": "New"}},
        roles=["everyone"],
    )
    assert result["ok"] is True
    assert result["updated_ids"] == [42]


def test_delete_requires_wildcard_right(executor, profile):
    _right("p1", "res.partner", ["name"], delete=True)
    # A right that doesn't cover "*" never authorizes delete (checked against
    # the "*" field explicitly, per odoo_cli_for_ai._delete).
    with pytest.raises(AuthorizationError):
        executor.execute("odoo_delete", "res.partner", {"profile_id": "p1", "id": 1}, roles=["everyone"])


def test_delete_success_with_wildcard_right(executor, profile):
    _right("p1", "res.partner", ["*"], delete=True)
    result = executor.execute(
        "odoo_delete", "res.partner", {"profile_id": "p1", "ids": [1, 2]}, roles=["everyone"],
    )
    assert result["ok"] is True
    assert result["deleted_ids"] == [1, 2]


def test_delete_requires_id_or_ids(executor, profile):
    _right("p1", "res.partner", ["*"], delete=True)
    with pytest.raises(ValidationError):
        executor.execute("odoo_delete", "res.partner", {"profile_id": "p1"}, roles=["everyone"])


def test_list_allowed_models_no_odoo_connection_needed(executor, profile):
    _right("p1", "res.partner", ["*"], read=True, create=True)
    _right("p1", "project.task", ["*"], read=True)
    result = executor.execute("odoo_list_allowed_models", "", {"profile_id": "p1"}, roles=["everyone"])
    models_by_name = {m["model"]: m for m in result["models"]}
    assert models_by_name["res.partner"]["create"] is True
    assert models_by_name["project.task"]["create"] is False


def test_list_allowed_fields_no_rights_configured(executor, profile):
    result = executor.execute(
        "odoo_list_allowed_fields", "res.partner", {"profile_id": "p1"}, roles=["everyone"],
    )
    assert result["ok"] is True
    assert result["fields"] == []
    assert "note" in result


def test_list_allowed_fields_wildcard_uses_full_schema(executor, profile, monkeypatch):
    _right("p1", "res.partner", ["*"], read=True)

    # Monkeypatch _build_client to return a FakeOdooClient with a schema.
    fake_client = odoo_cli_for_ai.OdooClient(schema={"name": {"type": "char", "string": "Name"}})

    def fake_build_client(profile_id):
        return fake_client, None

    monkeypatch.setattr(odoo_cli_for_ai, "_build_client", fake_build_client)
    result = executor.execute(
        "odoo_list_allowed_fields", "res.partner", {"profile_id": "p1"}, roles=["everyone"],
    )
    assert result["fields"][0]["name"] == "name"
    assert result["fields"][0]["read"] is True


def test_unknown_action_raises_validation_error(executor, profile):
    with pytest.raises(ValidationError):
        executor.execute("bogus_action", "res.partner", {"profile_id": "p1"}, roles=["everyone"])


def test_create_normalizes_html_fields(executor, profile, monkeypatch):
    _right("p1", "project.task", ["description"], create=True)
    fake_client = FakeOdooClient(schema={"description": {"type": "html"}})
    monkeypatch.setattr(odoo_cli_for_ai, "_build_client", lambda profile_id: (fake_client, None))

    result = executor.execute(
        "odoo_create", "project.task",
        {"profile_id": "p1", "values": {"description": "line1\nline2"}},
        roles=["everyone"],
    )
    assert result["ok"] is True
    posted_values = fake_client.calls[-1][1][1]
    assert posted_values["description"] == "<p>line1<br/>line2</p>"
