"""Signs opaque identity tokens for EXTERNAL MCP microservices to verify.

Not an authorization mechanism by itself — rights-plugin never decides what
an MCP tool call is allowed to do (see ``__init__.py``'s ``_pre_llm_call``
docstring and ``.agents/DECISIONS.md``, 2026-08-13: "chaque service MCP
reste responsable de son propre contrôle d'accès"). This module only lets a
resolved ``(platform, external_user_id, roles)`` identity travel through the
LLM to an external MCP tool call **without the LLM being able to forge or
tamper with it** — the LLM only ever sees/relays an opaque signed string, it
never has the signing key.

Format (compact, JWT-shaped, hand-rolled — no third-party dependency,
keeping this plugin's "stdlib only" convention, see
``.agents/CONVENTIONS.md``)::

    base64url(header_json) "." base64url(payload_json) "." base64url(signature)

``header`` carries ``{"alg": ..., "kid": ...}`` — the MCP-side verifier reads
this to pick which key/algorithm to check against, it is never hardcoded to
one algorithm. This is deliberate groundwork for a planned migration off
HMAC onto EdDSA (Ed25519, asymmetric — a compromised MCP can no longer forge
tokens for the others, only verify) — see ``.agents/DECISIONS.md``. Today
only ``HS256`` is implemented; adding an ``"EdDSA"`` entry to ``_SIGNERS``
later needs the ``cryptography`` package (already a dependency of
``odoo-plugin``, easy to justify here — but that's an interface/dependency
change to signal explicitly first, per ``AGENT.md``) and must NOT touch the
token *shape* — only add a new branch, so MCP verifiers written against
today's ``HS256`` tokens keep working unchanged during the transition.

``exp`` is short-lived (5 minutes by default) because this is a bearer
credential relayed through an LLM, which is a slow, log-heavy transport —
not because of any expected clock skew.

**One key per external MCP, managed as data (``models.McpSigningKey``),
not as a single global env var.** Each external microservice gets its own
``(kid, secret)`` registered via the dashboard/CLI, so a leaked/rotated key
for one MCP never affects the others, and adding/revoking one never
requires a container restart (the registry is read fresh on every call,
same as every other rights-plugin table). Because a turn doesn't know in
advance which external MCP tool (if any) the model will call,
``issue_mcp_identity_tokens`` signs **one token per active, supported key**
— ``_pre_llm_call`` injects one context line per token, each labelled by
its ``kid``/``label`` so the model can match it to the right MCP tool's
schema.

Never raises: any failure (bad key data, JSON error, an unsupported
``alg``) is logged and the offending key is skipped, not propagated into a
turn. An empty registry (no key configured yet) simply yields no tokens —
this must never break a chat turn or start injecting garbage by surprise,
same philosophy as every other bootstrap safety gate in this plugin (see
``.agents/DECISIONS.md``, "Garde-fous d'amorçage de `pre_tool_call`").
"""

from __future__ import annotations

import base64
import hashlib
import hmac as hmac_lib
import json
import logging
import os
import time
from typing import Any, Callable, Optional

import models

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
except ImportError:
    Ed25519PrivateKey = None  # EdDSA signing key registration still works; see _SIGNERS below —
    # a key already stored with alg="EdDSA" on a deployment without `cryptography` installed is
    # simply skipped (logged), same degrade-safely convention as rights_w_main/data_manager/
    # secret_service.py's keyring/Fernet imports (see requirements.txt).

logger = logging.getLogger(__name__)

ISSUER = "hermes-rights-plugin"
_DEFAULT_TTL_SECONDS = 300  # 5 minutes


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _json_compact(obj: dict[str, Any]) -> bytes:
    # sort_keys: signature must be deterministic for a given payload.
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sign_hmac(payload: dict[str, Any], key: models.McpSigningKey) -> str:
    header_b64 = _b64url(_json_compact({"alg": "HS256", "kid": key.id}))
    payload_b64 = _b64url(_json_compact(payload))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac_lib.new(key.secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url(signature)}"


def _sign_eddsa(payload: dict[str, Any], key: models.McpSigningKey) -> str:
    """``key.secret`` is the raw 32-byte Ed25519 private seed, base64url-encoded — exactly the
    shape `_save_mcp_signing_key`'s auto-generation already produces (`secrets.token_urlsafe(32)`
    IS a base64url encoding of 32 random bytes), so no change was needed there to support this.
    Header uses the JWT-standard spelling ``"EdDSA"`` (mixed case, RFC 8037) regardless of how
    `key.alg`/the `_SIGNERS` lookup key are cased — an external verifier (e.g. PyJWT) matches on
    this exact string."""
    padded = key.secret + "=" * (-len(key.secret) % 4)
    seed = base64.urlsafe_b64decode(padded.encode("ascii"))
    private_key = Ed25519PrivateKey.from_private_bytes(seed)

    header_b64 = _b64url(_json_compact({"alg": "EdDSA", "kid": key.id}))
    payload_b64 = _b64url(_json_compact(payload))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = private_key.sign(signing_input)
    return f"{header_b64}.{payload_b64}.{_b64url(signature)}"


def public_key_for(kid: str) -> Optional[str]:
    """Derives the standard-base64-encoded Ed25519 public key for signing key *kid*, in the exact
    shape an external verifying microservice typically expects for its own public-key env var
    (plain base64, not urlsafe — the two only ever disagree on '+/' vs '-_', but a caller pasting
    this into a .env must not have to guess which).
    Returns None if *kid* doesn't exist, isn't an EdDSA key, or `cryptography` isn't installed —
    never raises, so an operator script can print a clear message instead of a traceback."""
    if Ed25519PrivateKey is None:
        return None
    key = models.get_mcp_signing_key_or_none(kid)
    if key is None or (key.alg or "").upper() != "EDDSA":
        return None
    padded = key.secret + "=" * (-len(key.secret) % 4)
    seed = base64.urlsafe_b64decode(padded.encode("ascii"))
    public_bytes = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(
        encoding=Encoding.Raw, format=PublicFormat.Raw
    )
    return base64.b64encode(public_bytes).decode("ascii")


# alg name (McpSigningKey.alg, case-insensitive) -> signer. "EDDSA" is only registered when
# `cryptography` is importable (see the top-of-file try/except) — a key already stored with
# alg="EdDSA" on a deployment missing that dependency stays skipped (logged), never mis-signed as
# HMAC, same fail-closed posture as before this branch existed.
_SIGNERS: dict[str, Callable[[dict[str, Any], models.McpSigningKey], str]] = {
    "HS256": _sign_hmac,
}
if Ed25519PrivateKey is not None:
    _SIGNERS["EDDSA"] = _sign_eddsa

SUPPORTED_ALGS: tuple[str, ...] = tuple(_SIGNERS)


def issue_mcp_identity_tokens(*, platform: str, external_user_id: str, roles: list[str]) -> list[dict[str, str]]:
    """Sign one token per active, supported key in the registry.

    Returns a list of ``{"kid": ..., "label": ..., "token": ...}`` — empty
    if the registry has no active/supported key yet (e.g. before an
    operator configures the first external MCP). Guaranteed never to
    raise — see module docstring. Callers (today, only ``__init__.py``'s
    ``_pre_llm_call``) should treat an empty list as "inject nothing",
    never as an error to surface to the user.
    """
    try:
        keys = models.active_mcp_signing_keys()
    except Exception:
        logger.exception("rights-plugin: failed to list MCP signing keys — no MCP identity token issued this turn")
        return []

    try:
        ttl = int(os.environ.get("RIGHTS_MCP_TOKEN_TTL_SECONDS") or _DEFAULT_TTL_SECONDS)
        now = int(time.time())
        payload = {
            "iss": ISSUER,
            "sub": f"{platform}:{external_user_id}",
            "roles": list(roles),
            "iat": now,
            "exp": now + ttl,
        }
    except Exception:
        # e.g. RIGHTS_MCP_TOKEN_TTL_SECONDS set to a non-integer string —
        # must degrade to "no token this turn", never propagate into the
        # hook that called us (see module docstring).
        logger.exception("rights-plugin: failed to build MCP identity token payload — no token issued this turn")
        return []

    issued: list[dict[str, str]] = []
    for key in keys:
        signer = _SIGNERS.get((key.alg or "").upper())
        if signer is None:
            logger.warning(
                "rights-plugin: MCP signing key kid=%s uses unsupported alg=%s (supported: %s) — skipped",
                key.id, key.alg, SUPPORTED_ALGS,
            )
            continue
        try:
            token = signer(payload, key)
        except Exception:
            logger.exception("rights-plugin: failed to sign MCP identity token for kid=%s", key.id)
            continue
        issued.append({"kid": key.id, "label": key.label, "token": token})

    return issued
