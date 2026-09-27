"""token_signer.py — signed opaque identity tokens for external MCP microservices."""

from __future__ import annotations

import base64
import hashlib
import hmac as hmac_lib
import json
import time

import models
import token_signer


def _decode_segment(segment: str) -> dict:
    padded = segment + "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))


def test_no_keys_configured_yields_no_tokens():
    tokens = token_signer.issue_mcp_identity_tokens(platform="slack", external_user_id="U1", roles=["everyone"])
    assert tokens == []


def test_issues_one_token_per_active_key():
    models.create_mcp_signing_key("rag_mcp", "secret-a", label="RAG MCP")
    models.create_mcp_signing_key("odoo_reports_mcp", "secret-b", label="Odoo reports")
    tokens = token_signer.issue_mcp_identity_tokens(platform="slack", external_user_id="U1", roles=["everyone"])
    assert {t["kid"] for t in tokens} == {"rag_mcp", "odoo_reports_mcp"}
    assert {t["label"] for t in tokens} == {"RAG MCP", "Odoo reports"}
    for t in tokens:
        assert t["token"].count(".") == 2


def test_inactive_key_yields_no_token():
    models.create_mcp_signing_key("rag_mcp", "secret-a", active=False)
    tokens = token_signer.issue_mcp_identity_tokens(platform="slack", external_user_id="U1", roles=["everyone"])
    assert tokens == []


def test_unsupported_alg_key_is_skipped_not_raised():
    models.create_mcp_signing_key("rag_mcp", "secret-a", alg="RS256")  # never implemented
    tokens = token_signer.issue_mcp_identity_tokens(platform="slack", external_user_id="U1", roles=["everyone"])
    assert tokens == []


def test_alg_is_case_insensitive():
    models.create_mcp_signing_key("rag_mcp", "secret-a", alg="hs256")
    tokens = token_signer.issue_mcp_identity_tokens(platform="slack", external_user_id="U1", roles=["everyone"])
    assert len(tokens) == 1


def test_header_carries_alg_and_kid():
    models.create_mcp_signing_key("rag_mcp", "secret-a")
    tokens = token_signer.issue_mcp_identity_tokens(platform="slack", external_user_id="U1", roles=["everyone"])
    header = _decode_segment(tokens[0]["token"].split(".")[0])
    assert header == {"alg": "HS256", "kid": "rag_mcp"}


def test_payload_carries_issuer_subject_roles_and_expiry(monkeypatch):
    models.create_mcp_signing_key("rag_mcp", "secret-a")
    monkeypatch.setenv("RIGHTS_MCP_TOKEN_TTL_SECONDS", "60")
    before = int(time.time())
    tokens = token_signer.issue_mcp_identity_tokens(
        platform="slack", external_user_id="U0123", roles=["everyone", "manager"]
    )
    payload = _decode_segment(tokens[0]["token"].split(".")[1])
    assert payload["iss"] == "hermes-rights-plugin"
    assert payload["sub"] == "slack:U0123"
    assert payload["roles"] == ["everyone", "manager"]
    assert payload["iat"] >= before
    assert payload["exp"] == payload["iat"] + 60


def test_default_ttl_is_five_minutes(monkeypatch):
    models.create_mcp_signing_key("rag_mcp", "secret-a")
    monkeypatch.delenv("RIGHTS_MCP_TOKEN_TTL_SECONDS", raising=False)
    tokens = token_signer.issue_mcp_identity_tokens(platform="slack", external_user_id="U1", roles=["everyone"])
    payload = _decode_segment(tokens[0]["token"].split(".")[1])
    assert payload["exp"] - payload["iat"] == 300


def test_each_key_signs_with_its_own_secret():
    models.create_mcp_signing_key("rag_mcp", "secret-a")
    models.create_mcp_signing_key("odoo_reports_mcp", "secret-b")
    tokens = {t["kid"]: t["token"] for t in token_signer.issue_mcp_identity_tokens(
        platform="slack", external_user_id="U1", roles=["everyone"]
    )}

    for kid, secret in (("rag_mcp", "secret-a"), ("odoo_reports_mcp", "secret-b")):
        header_b64, payload_b64, sig_b64 = tokens[kid].split(".")
        expected = hmac_lib.new(secret.encode(), f"{header_b64}.{payload_b64}".encode("ascii"), hashlib.sha256).digest()
        padded = sig_b64 + "=" * (-len(sig_b64) % 4)
        assert base64.urlsafe_b64decode(padded.encode("ascii")) == expected

    # Cross-check: rag_mcp's token does NOT verify against odoo_reports_mcp's secret.
    header_b64, payload_b64, sig_b64 = tokens["rag_mcp"].split(".")
    wrong = hmac_lib.new(b"secret-b", f"{header_b64}.{payload_b64}".encode("ascii"), hashlib.sha256).digest()
    padded = sig_b64 + "=" * (-len(sig_b64) % 4)
    assert base64.urlsafe_b64decode(padded.encode("ascii")) != wrong


def test_never_raises_when_listing_keys_breaks(monkeypatch):
    def _raise():
        raise RuntimeError("boom")

    monkeypatch.setattr(models, "active_mcp_signing_keys", _raise)
    assert token_signer.issue_mcp_identity_tokens(platform="slack", external_user_id="U1", roles=["everyone"]) == []


def test_never_raises_on_bad_ttl_value(monkeypatch):
    models.create_mcp_signing_key("rag_mcp", "secret-a")
    monkeypatch.setenv("RIGHTS_MCP_TOKEN_TTL_SECONDS", "not-a-number")
    # The whole call must not blow up even though the ttl can't be parsed —
    # no token is a safe degradation, not a crashed turn.
    tokens = token_signer.issue_mcp_identity_tokens(platform="slack", external_user_id="U1", roles=["everyone"])
    assert tokens == []


def test_supported_algs_lists_hs256_and_eddsa():
    assert "HS256" in token_signer.SUPPORTED_ALGS
    assert "EDDSA" in token_signer.SUPPORTED_ALGS


# --- EdDSA (2026-09-22, see .agents/DECISIONS.md, "rights-plugin : signature EdDSA pour les
# jetons d'identité MCP") --------------------------------------------------------------------
#
# secrets.token_urlsafe(32) — what _save_mcp_signing_key auto-generates — is itself a base64url
# encoding of 32 random bytes, i.e. already a valid Ed25519 seed shape; tests below build their
# own fixed seed instead, so signature verification against an independently-derived public key
# is reproducible rather than depending on a fresh random key every run.

import base64 as _base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def _b64url_no_pad(data: bytes) -> str:
    return _base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


_FIXED_SEED = b"\x11" * 32
_FIXED_SEED_B64URL = _b64url_no_pad(_FIXED_SEED)


def test_eddsa_token_verifies_against_its_own_public_key():
    models.create_mcp_signing_key("sandbox", _FIXED_SEED_B64URL, alg="EdDSA")
    tokens = token_signer.issue_mcp_identity_tokens(platform="slack", external_user_id="U1", roles=["everyone"])
    assert len(tokens) == 1
    header_b64, payload_b64, sig_b64 = tokens[0]["token"].split(".")

    public_key = Ed25519PrivateKey.from_private_bytes(_FIXED_SEED).public_key()
    sig_padded = sig_b64 + "=" * (-len(sig_b64) % 4)
    signature = _base64.urlsafe_b64decode(sig_padded.encode("ascii"))
    public_key.verify(signature, f"{header_b64}.{payload_b64}".encode("ascii"))  # raises if invalid


def test_eddsa_header_uses_standard_jwt_spelling():
    models.create_mcp_signing_key("sandbox", _FIXED_SEED_B64URL, alg="EdDSA")
    tokens = token_signer.issue_mcp_identity_tokens(platform="slack", external_user_id="U1", roles=["everyone"])
    header = _decode_segment(tokens[0]["token"].split(".")[0])
    # Mixed-case "EdDSA" (RFC 8037), not "EDDSA" — the dict key used to look up the signer is
    # uppercased internally, but the wire format must match what a PyJWT verifier expects exactly.
    assert header == {"alg": "EdDSA", "kid": "sandbox"}


def test_eddsa_alg_is_case_insensitive_like_hmac():
    models.create_mcp_signing_key("sandbox", _FIXED_SEED_B64URL, alg="eddsa")
    tokens = token_signer.issue_mcp_identity_tokens(platform="slack", external_user_id="U1", roles=["everyone"])
    assert len(tokens) == 1


def test_hmac_and_eddsa_keys_coexist():
    models.create_mcp_signing_key("rag_mcp", "secret-a", alg="HS256")
    models.create_mcp_signing_key("sandbox", _FIXED_SEED_B64URL, alg="EdDSA")
    tokens = {t["kid"]: t for t in token_signer.issue_mcp_identity_tokens(
        platform="slack", external_user_id="U1", roles=["everyone"]
    )}
    assert set(tokens) == {"rag_mcp", "sandbox"}
    assert _decode_segment(tokens["rag_mcp"]["token"].split(".")[0])["alg"] == "HS256"
    assert _decode_segment(tokens["sandbox"]["token"].split(".")[0])["alg"] == "EdDSA"


def test_public_key_for_matches_the_signing_key():
    models.create_mcp_signing_key("sandbox", _FIXED_SEED_B64URL, alg="EdDSA")
    public_b64 = token_signer.public_key_for("sandbox")

    expected = Ed25519PrivateKey.from_private_bytes(_FIXED_SEED).public_key().public_bytes(
        encoding=Encoding.Raw, format=PublicFormat.Raw
    )
    assert _base64.b64decode(public_b64) == expected
    # Plain base64, not urlsafe — matches a typical external verifier's expected format exactly.
    Ed25519PublicKey.from_public_bytes(_base64.b64decode(public_b64))  # raises if malformed


def test_public_key_for_unknown_kid_returns_none():
    assert token_signer.public_key_for("does-not-exist") is None


def test_public_key_for_hmac_key_returns_none():
    models.create_mcp_signing_key("rag_mcp", "secret-a", alg="HS256")
    assert token_signer.public_key_for("rag_mcp") is None
