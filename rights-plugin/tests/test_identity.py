"""rights_plugin.identity.resolve_identity — platform/session resolution + roles."""

from identity import ROLE_AUTOMATION, ROLE_EVERYONE, resolve_identity
from models import bind_role


def test_direct_platform_and_user_id_no_lookup_needed():
    # pre_llm_call style: platform/sender_id given directly.
    identity = resolve_identity(platform="slack", external_user_id="U0123")
    assert identity.platform == "slack"
    assert identity.external_user_id == "U0123"


def test_direct_identity_includes_bound_roles_plus_everyone():
    bind_role("slack", "U0123", ["admin", "finance"])
    identity = resolve_identity(platform="slack", external_user_id="U0123")
    assert set(identity.roles) == {"admin", "finance", ROLE_EVERYONE}


def test_direct_identity_with_no_binding_gets_only_everyone():
    identity = resolve_identity(platform="slack", external_user_id="ghost")
    assert identity.roles == [ROLE_EVERYONE]


def test_session_id_resolves_via_session_db(fake_sessions):
    # pre_tool_call style: only session_id given, resolved via the fake SessionDB.
    fake_sessions["sess-1"] = {"source": "telegram", "user_id": "42"}
    bind_role("telegram", "42", ["reader"])
    identity = resolve_identity(session_id="sess-1")
    assert identity.platform == "telegram"
    assert identity.external_user_id == "42"
    assert set(identity.roles) == {"reader", ROLE_EVERYONE}


def test_session_id_not_found_falls_back_to_automation(fake_sessions):
    identity = resolve_identity(session_id="missing-session")
    assert identity.platform == "automation"
    assert set(identity.roles) == {ROLE_AUTOMATION, ROLE_EVERYONE}


def test_session_missing_user_id_falls_back_to_automation(fake_sessions):
    fake_sessions["sess-2"] = {"source": "slack", "user_id": None}
    identity = resolve_identity(session_id="sess-2")
    assert identity.platform == "automation"
    assert ROLE_AUTOMATION in identity.roles


def test_no_identity_information_at_all_falls_back_to_automation():
    identity = resolve_identity()
    assert identity.platform == "automation"
    assert identity.external_user_id == "cron"
    assert set(identity.roles) == {ROLE_AUTOMATION, ROLE_EVERYONE}


def test_direct_platform_takes_priority_over_session_id(fake_sessions):
    fake_sessions["sess-1"] = {"source": "telegram", "user_id": "42"}
    # Both given — direct platform/user_id wins, no SessionDB lookup happens.
    identity = resolve_identity(session_id="sess-1", platform="slack", external_user_id="U9")
    assert identity.platform == "slack"
    assert identity.external_user_id == "U9"


def test_roles_are_deduplicated_and_sorted():
    bind_role("slack", "U1", ["zebra", "everyone", "admin"])
    identity = resolve_identity(platform="slack", external_user_id="U1")
    assert identity.roles == ["admin", "everyone", "zebra"]
