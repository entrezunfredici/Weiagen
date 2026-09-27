"""rights_plugin.models — McpSigningKey CRUD (one signing key per EXTERNAL
MCP microservice, see ../token_signer.py)."""

import models
from models import (
    active_mcp_signing_keys,
    create_mcp_signing_key,
    delete_mcp_signing_key,
    get_mcp_signing_key,
    get_mcp_signing_key_or_none,
    list_mcp_signing_keys,
)
from rights_w_main.errors_manager.errors import NotFoundError

import pytest


def test_create_mcp_signing_key_minimal():
    key = create_mcp_signing_key("rag_mcp", "s3cret")
    assert key.id == "rag_mcp"
    assert key.secret == "s3cret"
    assert key.alg == "HS256"
    assert key.active is True
    assert key.created_at > 0


def test_create_mcp_signing_key_with_label_and_alg():
    key = create_mcp_signing_key("rag_mcp", "s3cret", label="RAG MCP", alg="HS256", active=False)
    assert key.label == "RAG MCP"
    assert key.active is False


def test_create_mcp_signing_key_upserts_by_kid():
    create_mcp_signing_key("rag_mcp", "first-secret")
    create_mcp_signing_key("rag_mcp", "second-secret")
    assert get_mcp_signing_key("rag_mcp").secret == "second-secret"
    assert len(list_mcp_signing_keys()) == 1


def test_create_mcp_signing_key_preserves_created_at_on_update_by_default():
    first = create_mcp_signing_key("rag_mcp", "first-secret")
    second = create_mcp_signing_key("rag_mcp", "second-secret")
    assert second.created_at == first.created_at


def test_create_mcp_signing_key_created_at_can_be_overridden():
    key = create_mcp_signing_key("rag_mcp", "s3cret", created_at=12345)
    assert key.created_at == 12345


def test_get_mcp_signing_key_missing_raises_not_found():
    with pytest.raises(NotFoundError):
        get_mcp_signing_key("missing")


def test_get_mcp_signing_key_or_none_missing_returns_none():
    assert get_mcp_signing_key_or_none("missing") is None


def test_delete_mcp_signing_key():
    create_mcp_signing_key("rag_mcp", "s3cret")
    assert delete_mcp_signing_key("rag_mcp") is True
    assert get_mcp_signing_key_or_none("rag_mcp") is None
    assert delete_mcp_signing_key("rag_mcp") is False


def test_list_mcp_signing_keys_returns_all():
    create_mcp_signing_key("rag_mcp", "s1")
    create_mcp_signing_key("odoo_reports_mcp", "s2")
    assert {k.id for k in list_mcp_signing_keys()} == {"rag_mcp", "odoo_reports_mcp"}


def test_active_mcp_signing_keys_filters_out_inactive():
    create_mcp_signing_key("rag_mcp", "s1", active=True)
    create_mcp_signing_key("odoo_reports_mcp", "s2", active=False)
    assert [k.id for k in active_mcp_signing_keys()] == ["rag_mcp"]


def test_active_mcp_signing_keys_empty_by_default():
    assert active_mcp_signing_keys() == []
