"""w_odoo.odoo_cli_for_config.OdooConfigExecutor — profile/right CRUD action dispatch."""

import pytest

from w_main.errors_manager.errors import NotFoundError, ValidationError
from w_odoo.odoo_cli_for_config import OdooConfigExecutor


@pytest.fixture
def config():
    return OdooConfigExecutor()


def test_unknown_action_raises_validation_error(config):
    with pytest.raises(ValidationError):
        config.execute("bogus", {})


def test_save_profile_requires_id(config):
    with pytest.raises(ValidationError):
        config.execute("save_profile", {"base_url": "https://x", "database": "db", "login": "l"})


def test_save_profile_requires_base_url_database_login(config):
    with pytest.raises(ValidationError):
        config.execute("save_profile", {"id": "p1"})


def test_save_profile_success_password_not_echoed(config):
    result = config.execute("save_profile", {
        "id": "p1", "base_url": "https://odoo.example.com", "database": "db",
        "login": "ai@example.com", "password": "s3cret",
    })
    assert result["ok"] is True
    assert "password" not in result["profile"]
    assert result["profile"]["id"] == "p1"
    assert result["profile"]["label"] == "p1"  # defaults to id when omitted


def test_save_profile_defaults_port_443(config):
    result = config.execute("save_profile", {
        "id": "p1", "base_url": "https://x", "database": "db", "login": "l",
    })
    assert result["profile"]["port"] == 443


def test_list_profiles(config):
    config.execute("save_profile", {"id": "p1", "base_url": "https://x", "database": "db", "login": "l"})
    config.execute("save_profile", {"id": "p2", "base_url": "https://x", "database": "db", "login": "l"})
    result = config.execute("list_profiles", {})
    assert result["count"] == 2


def test_get_profile_requires_id(config):
    with pytest.raises(ValidationError):
        config.execute("get_profile", {})


def test_get_profile_missing_raises_not_found(config):
    with pytest.raises(NotFoundError):
        config.execute("get_profile", {"id": "missing"})


def test_get_profile_success(config):
    config.execute("save_profile", {"id": "p1", "base_url": "https://x", "database": "db", "login": "l"})
    result = config.execute("get_profile", {"id": "p1"})
    assert result["profile"]["id"] == "p1"


def test_delete_profile_requires_id(config):
    with pytest.raises(ValidationError):
        config.execute("delete_profile", {})


def test_delete_profile(config):
    config.execute("save_profile", {"id": "p1", "base_url": "https://x", "database": "db", "login": "l"})
    result = config.execute("delete_profile", {"id": "p1"})
    assert result["deleted"] is True


# Right *management* is generalized through the rights plugin (see
# w_odoo/rights_bridge.py and .agents/DECISIONS.md) — save_right/
# delete_right still exist here (backing the odoo-plugin dashboard's Rights
# section) but delegate to rights_bridge.create_right/delete_right instead
# of owning the data. "list_rights" is read-only, reshaping. get_right was
# never restored (unused by the dashboard). Tests below create AccessRight
# rows directly via rights-plugin's own models module for the read-side
# assertions, matching what real writes through rights_bridge produce.

def _access_right(profile_id: str, odoo_model: str, **kwargs):
    import models
    return models.create_access_right(
        roles=["everyone"], resource_type="odoo_model",
        resource_id=f"{profile_id}:{odoo_model}", **kwargs,
    )


def test_list_rights_reshapes_access_right_into_odoo_right_shape(config):
    _access_right("p1", "res.partner", fields=["name", "email"], read=True, create=True)
    result = config.execute("list_rights", {})
    assert result["count"] == 1
    right = result["rights"][0]
    assert right["profile_id"] == "p1"
    assert right["odoo_model"] == "res.partner"
    assert right["fields"] == ["name", "email"]
    assert right["read"] is True
    assert right["create"] is True


def test_list_rights_filtered_by_profile(config):
    _access_right("p1", "res.partner")
    _access_right("p2", "res.partner")
    result = config.execute("list_rights", {"profile_id": "p1"})
    assert result["count"] == 1


def test_list_rights_unfiltered(config):
    _access_right("p1", "res.partner")
    _access_right("p2", "res.partner")
    result = config.execute("list_rights", {})
    assert result["count"] == 2


def test_get_right_action_no_longer_exists(config):
    with pytest.raises(ValidationError):
        config.execute("get_right", {})


def test_save_right_requires_profile_id_and_model(config):
    with pytest.raises(ValidationError):
        config.execute("save_right", {"profile_id": "p1"})
    with pytest.raises(ValidationError):
        config.execute("save_right", {"odoo_model": "res.partner"})


def test_save_right_creates_a_real_access_right_via_rights_bridge(config):
    result = config.execute("save_right", {
        "profile_id": "p1", "odoo_model": "res.partner", "fields": "name, email",
        "create": True, "require_confirmation": True,
    })
    assert result["ok"] is True
    right = result["right"]
    assert right["profile_id"] == "p1"
    assert right["odoo_model"] == "res.partner"
    assert right["fields"] == ["name", "email"]
    assert right["create"] is True
    assert right["require_confirmation"] is True

    import models
    stored = models.get_access_right(right["id"])
    assert stored.roles == ["everyone"]
    assert stored.resource_type == "odoo_model"
    assert stored.resource_id == "p1:res.partner"


def test_save_right_fields_defaults_to_wildcard_when_empty(config):
    result = config.execute("save_right", {"profile_id": "p1", "odoo_model": "res.partner", "fields": ""})
    assert result["right"]["fields"] == ["*"]


def test_save_right_defaults_read_true_others_false(config):
    result = config.execute("save_right", {"profile_id": "p1", "odoo_model": "res.partner"})
    right = result["right"]
    assert right["read"] is True
    assert right["create"] is False
    assert right["update"] is False
    assert right["delete"] is False


def test_delete_right_requires_id(config):
    with pytest.raises(ValidationError):
        config.execute("delete_right", {})


def test_delete_right_deletes_via_rights_bridge(config):
    saved = config.execute("save_right", {"id": "r1", "profile_id": "p1", "odoo_model": "res.partner"})
    result = config.execute("delete_right", {"id": saved["right"]["id"]})
    assert result["deleted"] is True

    import models
    assert models.get_access_right_or_none("r1") is None


def test_list_odoo_models_requires_profile_id(config):
    with pytest.raises(ValidationError):
        config.execute("list_odoo_models", {})


def test_list_odoo_fields_requires_profile_id_and_model(config):
    with pytest.raises(ValidationError):
        config.execute("list_odoo_fields", {"profile_id": "p1"})
