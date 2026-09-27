"""Generic identity→role bindings and deny-by-default access rights.

Four models, all persisted via the vendored ``rights_w_main.data_manager.SDKTable``
(JSON file, same pattern as ``odoo-plugin``'s ``OdooProfile``/``OdooRight``):

- ``Role`` — a named entry in the role catalog, managed independently of
  who holds it (``RoleBinding``) or what it grants (``AccessRight``). Purely
  organizational: nothing else in this module enforces that a role string
  used elsewhere actually has a catalog entry — see ``applies_to_role`` /
  ``bind_role`` — but the dashboard's pickers are populated from it, and it
  gives an operator a place to attach a human label/description to what
  would otherwise just be a bare string like ``"admin"``.
- ``RoleBinding`` — maps one external identity (``platform`` +
  ``external_user_id``, e.g. Slack user id) to zero or more role names.
  Platform-agnostic on purpose: Hermes isn't Slack-only.
- ``AccessRight`` — the generalized replacement for ``odoo-plugin``'s
  ``OdooRight``: ``(roles, resource_type, resource_id, fields) -> CRUD(+execute)
  + confirmation``. ``roles`` (plural, a list) lets one right apply to
  several roles at once instead of requiring a duplicate right per role.
  ``resource_type``/``resource_id`` are opaque strings from this module's
  point of view — e.g. ``odoo-plugin`` uses ``resource_type="odoo_model"``,
  ``resource_id=f"{profile_id}:{model}"``; ``rights_plugin``'s own
  ``pre_tool_call`` hook uses ``resource_type="hermes_tool"``,
  ``resource_id=<tool_name>``. That composition is each caller's
  convention, not a feature of this module.
- ``DirectoryEntry`` — a cached, best-effort "who is who" row per platform
  (today: Slack workspace members), used only to populate a pick-list in the
  dashboard's role-binding form instead of requiring an admin to copy/paste
  a raw platform user id by hand. Never consulted by ``engine.py``'s
  authorization decisions — purely a UX convenience. See ``directory.py``
  for how it's kept (lazily) fresh.

Named ``AccessRight``, not ``Right`` — ``Right`` is already the vendored
``rights_w_main.right_manager.right_manager.Right`` dataclass this model converts
to via ``to_right()`` (same reason ``odoo-plugin`` names its persisted model
``OdooRight`` rather than ``Right``).

``AccessRight.role`` (singular string) was renamed to ``roles`` (list) on
2026-08-18 — see ``migrate_access_right_role_field()`` below for the
one-time schema migration of already-stored data, and
``.agents/DECISIONS.md`` for why this is a signalled public-interface
change (``rights_plugin_api.create_right``'s signature changed too).
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable

from hermes_constants import get_hermes_home
from rights_w_main.data_manager import BoolField, IntField, ListField, SDKModel, SDKTable, StringField
from rights_w_main.right_manager.right_manager import Right

# Fallback data directory if RIGHTS_ROLE_BINDINGS_PATH/RIGHTS_ACCESS_RIGHTS_PATH
# aren't set — computed the same way __init__.py's os.environ.setdefault()
# does, NOT relied upon to have already run: odoo-plugin/__init__.py imports
# w_odoo.rights_bridge eagerly at its own module load time, and plugins
# load alphabetically ("odoo" before "rights"), so rights_bridge ->
# rights_plugin_api -> this module can be imported (and these os.getenv()
# calls below executed) *before* rights-plugin/__init__.py ever runs its own
# setdefault() — confirmed on test-server: without this, both tables silently fell
# back to a literal "/workspace/..." path that doesn't exist in the
# container, and the OdooRight -> AccessRight migration crashed on first
# write (see .agents/CHANGELOG_AGENT.md, 2026-08-13). Must not depend on
# import order.
_FALLBACK_DATA_DIR = get_hermes_home() / "rights-plugin-data"

# ---------------------------------------------------------------------------
# Role — the catalog. Purely organizational (see module docstring): nothing
# here enforces that a role string used in RoleBinding.roles/AccessRight.roles
# has a matching catalog entry.
# ---------------------------------------------------------------------------


class Role(SDKModel):
    """One entry in the role catalog."""

    id: str = StringField(primary_key=True)  # the slug itself, e.g. "admin" —
    # the same string referenced in RoleBinding.roles/AccessRight.roles, not
    # a separate opaque id.
    label: str = StringField(default="")
    description: str = StringField(default="")


_ROLES_PATH = os.getenv(
    "RIGHTS_ROLES_PATH",
    str(_FALLBACK_DATA_DIR / "roles.json"),
)

_roles_table: SDKTable = SDKTable(
    Role,
    file_path=_ROLES_PATH,
    keyring_service="rights-plugin",
)


def create_role(id: str, *, label: str = "", description: str = "") -> Role:
    """Create or update a role catalog entry (upsert by id, same convention
    as create_access_right/bind_role)."""
    role = Role(id=id, label=label, description=description)
    _roles_table.save(role)
    return role


def get_role(role_id: str) -> Role:
    return _roles_table.get(role_id)


def get_role_or_none(role_id: str) -> Role | None:
    return _roles_table.get_or_none(role_id)


def save_role(role: Role) -> None:
    _roles_table.save(role)


def delete_role(role_id: str) -> bool:
    return _roles_table.delete(role_id)


def list_roles() -> list[Role]:
    return _roles_table.list()


def list_roles_public() -> list[dict]:
    return _roles_table.list_public()


# ---------------------------------------------------------------------------
# RoleBinding
# ---------------------------------------------------------------------------


class RoleBinding(SDKModel):
    """One external identity → zero or more role names."""

    id: str = StringField(primary_key=True)  # f"{platform}:{external_user_id}" by convention
    platform: str = StringField()  # "slack" | "telegram" | "cli" | "automation" | ...
    external_user_id: str = StringField()
    roles: list = ListField()
    label: str = StringField(default="")


_ROLE_BINDINGS_PATH = os.getenv(
    "RIGHTS_ROLE_BINDINGS_PATH",
    str(_FALLBACK_DATA_DIR / "role-bindings.json"),
)

_role_bindings_table: SDKTable = SDKTable(
    RoleBinding,
    file_path=_ROLE_BINDINGS_PATH,
    keyring_service="rights-plugin",
)


def _binding_id(platform: str, external_user_id: str) -> str:
    return f"{platform}:{external_user_id}"


def bind_role(
    platform: str,
    external_user_id: str,
    roles: list[str],
    *,
    label: str = "",
) -> RoleBinding:
    """Create or replace the role binding for one identity (upsert by (platform, external_user_id))."""
    binding = RoleBinding(
        id=_binding_id(platform, external_user_id),
        platform=platform,
        external_user_id=external_user_id,
        roles=list(roles),
        label=label,
    )
    _role_bindings_table.save(binding)
    return binding


def get_role_binding(binding_id: str) -> RoleBinding:
    return _role_bindings_table.get(binding_id)


def get_role_binding_or_none(binding_id: str) -> RoleBinding | None:
    return _role_bindings_table.get_or_none(binding_id)


def get_role_binding_for_identity(platform: str, external_user_id: str) -> RoleBinding | None:
    """Look up a binding by (platform, external_user_id) directly, no id needed."""
    return _role_bindings_table.get_or_none(_binding_id(platform, external_user_id))


def unbind_role(platform: str, external_user_id: str) -> bool:
    return _role_bindings_table.delete(_binding_id(platform, external_user_id))


def list_role_bindings() -> list[RoleBinding]:
    return _role_bindings_table.list()


def list_role_bindings_public() -> list[dict]:
    return _role_bindings_table.list_public()


def role_bindings_for_platform(platform: str) -> list[RoleBinding]:
    return [b for b in _role_bindings_table.list() if b.platform == platform]


# ---------------------------------------------------------------------------
# AccessRight
# ---------------------------------------------------------------------------


class AccessRight(SDKModel):
    """Generalized deny-by-default rule: what a role may do on a resource."""

    # Identity
    id: str = StringField(primary_key=True)
    label: str = StringField(default="")

    # Scope
    roles: list = ListField()  # e.g. ["everyone"], ["admin", "finance"] — one right, several roles
    resource_type: str = StringField()  # e.g. "odoo_model", "hermes_tool"
    resource_id: str = StringField()  # e.g. "1:project.task", "shell_exec", "*"
    fields: list = ListField(default_factory=lambda: ["*"])

    # Operation flags (deny-by-default)
    create: bool = BoolField(default=False)
    read: bool = BoolField(default=True)
    update: bool = BoolField(default=False)
    delete: bool = BoolField(default=False)
    execute: bool = BoolField(default=False)

    # Confirmation flags (per-operation; require_confirmation is the global fallback)
    require_confirmation: bool = BoolField(default=False)
    confirm_create: bool = BoolField(default=False)
    confirm_read: bool = BoolField(default=False)
    confirm_update: bool = BoolField(default=False)
    confirm_delete: bool = BoolField(default=False)
    confirm_execute: bool = BoolField(default=False)

    def applies_to_field(self, field_name: str) -> bool:
        """True if this right covers the given field (or covers all via '*')."""
        return "*" in self.fields or field_name in self.fields

    def applies_to_role(self, role: str) -> bool:
        """True if this right applies to the given role — plain membership,
        no wildcard (unlike fields/resource_id): a role is either explicitly
        listed or it isn't, "*" has no special meaning here."""
        return role in self.roles

    def applies_to_resource(self, resource_id: str) -> bool:
        """True if this right covers the given resource id (or covers all via '*')."""
        return self.resource_id == "*" or self.resource_id == resource_id

    def to_right(self) -> Right:
        """Convert to a RightManager-compatible Right dataclass.

        Same ``x or None`` cascade as ``odoo-plugin``'s ``OdooRight.to_right()``:
        a per-operation confirm_* flag can only ever inherit the global
        ``require_confirmation`` (when stored ``False``) or force confirmation
        on (when stored ``True``) — it can never force a single operation's
        confirmation *off* while the global flag is on. Same limitation as
        before, preserved deliberately rather than silently changed.
        """
        return Right(
            id=self.id,
            create=self.create,
            read=self.read,
            update=self.update,
            delete=self.delete,
            execute=self.execute,
            require_confirmation=self.require_confirmation,
            confirm_create=self.confirm_create or None,
            confirm_read=self.confirm_read or None,
            confirm_update=self.confirm_update or None,
            confirm_delete=self.confirm_delete or None,
            confirm_execute=self.confirm_execute or None,
        )


_ACCESS_RIGHTS_PATH = os.getenv(
    "RIGHTS_ACCESS_RIGHTS_PATH",
    str(_FALLBACK_DATA_DIR / "access-rights.json"),
)

_access_rights_table: SDKTable = SDKTable(
    AccessRight,
    file_path=_ACCESS_RIGHTS_PATH,
    keyring_service="rights-plugin",
)


def create_access_right(
    roles: list[str],
    resource_type: str,
    resource_id: str,
    *,
    fields: list[str] | None = None,
    label: str = "",
    id: str | None = None,
    create: bool = False,
    read: bool = True,
    update: bool = False,
    delete: bool = False,
    execute: bool = False,
    require_confirmation: bool = False,
    confirm_create: bool = False,
    confirm_read: bool = False,
    confirm_update: bool = False,
    confirm_delete: bool = False,
    confirm_execute: bool = False,
) -> AccessRight:
    # hermes_tool/hermes_cron have no field concept at all (a bare tool or
    # cron call has no "fields" the way an Odoo model record does) — force
    # fields=["*"] regardless of what was submitted. Without this, a right
    # whose fields is anything other than ["*"] (e.g. someone typing the
    # tool name into the Fields box, expecting it to scope the right to
    # that tool) silently becomes 100% inert: engine.check_right always
    # evaluates hermes_tool/hermes_cron with field="*" (see
    # rights_plugin/__init__.py::_pre_tool_call, which never passes a
    # field), and AccessRight.applies_to_field("*") is only true when
    # "*" itself is literally in `fields` — a real production bug caught
    # 2026-08-20, see .agents/DECISIONS.md. Applies at this single choke
    # point so it holds regardless of entry point (dashboard, CLI,
    # rights_plugin_api, migration).
    if resource_type in ("hermes_tool", "hermes_cron"):
        fields = ["*"]
    right = AccessRight(
        id=id or str(uuid.uuid4()),
        label=label,
        roles=list(roles),
        resource_type=resource_type,
        resource_id=resource_id,
        fields=fields if fields is not None else ["*"],
        create=create,
        read=read,
        update=update,
        delete=delete,
        execute=execute,
        require_confirmation=require_confirmation,
        confirm_create=confirm_create,
        confirm_read=confirm_read,
        confirm_update=confirm_update,
        confirm_delete=confirm_delete,
        confirm_execute=confirm_execute,
    )
    _access_rights_table.save(right)
    return right


def normalize_hermes_resource_fields() -> int:
    """Idempotent self-heal: force ``fields=["*"]`` on any existing
    hermes_tool/hermes_cron right that doesn't already have it.

    Real bug caught 2026-08-20 (see .agents/DECISIONS.md): before
    create_access_right() started forcing this at write time, a right
    saved with any other ``fields`` value (e.g. typing a tool name into
    the dashboard's Fields box, expecting it to scope the right to that
    tool) became 100% inert — engine.check_right always evaluates
    hermes_tool/hermes_cron with field="*" (see rights_plugin/__init__.py
    ::_pre_tool_call, which never passes a field), so a right whose
    fields doesn't literally contain "*" silently denies everything,
    including the resource_id it was meant to cover. This repairs rows
    saved before that fix without a manual data edit on every deployment
    — safe to call on every plugin load (same pattern as
    migrate_odoo_rights.maybe_migrate_odoo_rights_on_load). Returns how
    many rights were corrected (0 on a normal, already-clean load).
    """
    fixed = 0
    for right in list_access_rights():
        if right.resource_type in ("hermes_tool", "hermes_cron") and right.fields != ["*"]:
            create_access_right(
                roles=right.roles,
                resource_type=right.resource_type,
                resource_id=right.resource_id,
                fields=["*"],
                label=right.label,
                id=right.id,
                create=right.create,
                read=right.read,
                update=right.update,
                delete=right.delete,
                execute=right.execute,
                require_confirmation=right.require_confirmation,
                confirm_create=right.confirm_create,
                confirm_read=right.confirm_read,
                confirm_update=right.confirm_update,
                confirm_delete=right.confirm_delete,
                confirm_execute=right.confirm_execute,
            )
            fixed += 1
    return fixed


def get_access_right(right_id: str) -> AccessRight:
    return _access_rights_table.get(right_id)


def get_access_right_or_none(right_id: str) -> AccessRight | None:
    return _access_rights_table.get_or_none(right_id)


def save_access_right(right: AccessRight) -> None:
    _access_rights_table.save(right)


def delete_access_right(right_id: str) -> bool:
    return _access_rights_table.delete(right_id)


def list_access_rights() -> list[AccessRight]:
    return _access_rights_table.list()


def list_access_rights_public() -> list[dict]:
    return _access_rights_table.list_public()


# ---------------------------------------------------------------------------
# Filtered lookups
# ---------------------------------------------------------------------------


def _filter(predicate: Callable[[AccessRight], bool]) -> list[AccessRight]:
    return [r for r in _access_rights_table.list() if predicate(r)]


def rights_for_role(role: str) -> list[AccessRight]:
    """All rights bound to a given role (a right may also be bound to others)."""
    return _filter(lambda r: r.applies_to_role(role))


def rights_for_resource_type(resource_type: str) -> list[AccessRight]:
    """All rights that apply to a given resource type, across every role."""
    return _filter(lambda r: r.resource_type == resource_type)


def rights_for_resource(resource_type: str, resource_id: str) -> list[AccessRight]:
    """All rights (any role) that cover a specific resource (exact match or '*')."""
    return _filter(
        lambda r: r.resource_type == resource_type and r.applies_to_resource(resource_id)
    )


def rights_for_role_and_resource(role: str, resource_type: str, resource_id: str) -> list[AccessRight]:
    """All rights bound to one role (among possibly several) that cover a
    specific resource (exact match or '*')."""
    return _filter(
        lambda r: r.applies_to_role(role)
        and r.resource_type == resource_type
        and r.applies_to_resource(resource_id)
    )


def rights_for_roles_and_resource_type(roles: list[str], resource_type: str) -> list[AccessRight]:
    """All rights (any resource_id) whose roles intersect the given roles,
    for a resource type.

    Bulk-listing counterpart to rights_for_role_and_resource — used by
    consumers that need to enumerate every right covering a resource_type
    (e.g. odoo-plugin's odoo_sdk_list_allowed_models/_fields) rather than
    check one resource at a time.
    """
    role_set = set(roles)
    return _filter(lambda r: role_set.intersection(r.roles) and r.resource_type == resource_type)


# ---------------------------------------------------------------------------
# DirectoryEntry — cached "who is who" per platform (e.g. Slack workspace
# members), so the dashboard can offer a pick-list instead of requiring an
# admin to copy/paste a raw platform user id by hand when creating a
# RoleBinding. Purely a UX convenience, never consulted by engine.py's
# authorization decisions — see directory.py for the sync logic.
# ---------------------------------------------------------------------------


class DirectoryEntry(SDKModel):
    """One cached "who is who" row for one identity on one platform."""

    id: str = StringField(primary_key=True)  # f"{platform}:{external_user_id}"
    platform: str = StringField()  # "slack" today; other platforms are an extension point
    external_user_id: str = StringField()
    display_name: str = StringField(default="")
    real_name: str = StringField(default="")
    email: str = StringField(default="")
    synced_at: int = IntField(default=0)  # unix epoch seconds of the sync batch that wrote this row


_DIRECTORY_ENTRIES_PATH = os.getenv(
    "RIGHTS_DIRECTORY_ENTRIES_PATH",
    str(_FALLBACK_DATA_DIR / "directory-entries.json"),
)

_directory_table: SDKTable = SDKTable(
    DirectoryEntry,
    file_path=_DIRECTORY_ENTRIES_PATH,
    keyring_service="rights-plugin",
)


def list_directory_entries(platform: str | None = None) -> list[DirectoryEntry]:
    entries = _directory_table.list()
    if platform:
        entries = [e for e in entries if e.platform == platform]
    return entries


def directory_last_synced_at(platform: str) -> int:
    """Unix epoch seconds of the most recent sync for this platform, or 0 if never synced."""
    return max((e.synced_at for e in list_directory_entries(platform)), default=0)


def replace_directory_entries(platform: str, entries: list[dict]) -> list[DirectoryEntry]:
    """Atomically replace the cached directory for one platform (full sync,
    not an incremental merge — someone who left the workspace must disappear
    from the pick-list, not linger from a stale row)."""
    for existing in list_directory_entries(platform):
        _directory_table.delete(existing.id)

    synced_at = int(time.time())
    saved: list[DirectoryEntry] = []
    for raw in entries:
        entry = DirectoryEntry(
            id=f"{platform}:{raw['external_user_id']}",
            platform=platform,
            external_user_id=str(raw["external_user_id"]),
            display_name=str(raw.get("display_name") or ""),
            real_name=str(raw.get("real_name") or ""),
            email=str(raw.get("email") or ""),
            synced_at=synced_at,
        )
        _directory_table.save(entry)
        saved.append(entry)
    return saved


# ---------------------------------------------------------------------------
# McpSigningKey — one signing key per EXTERNAL MCP microservice consuming
# token_signer.py's identity tokens (see that module's docstring). Unlike
# every other model here, this one holds a real secret (a shared HMAC key,
# later possibly an Ed25519 private key) — stored in plain JSON like
# everything else in this file (no SecretField/Fernet encryption, see
# ``../.agents/DECISIONS.md`` for why that's a deliberate deferral, not an
# oversight). Managed via the dashboard/CLI instead of a docker-compose env
# var specifically so adding, rotating, or revoking a key never requires a
# container restart — same "relu à chaque appel" property as every other
# table in this module (see [[rights-plugin-gating-gotchas]]).
# ---------------------------------------------------------------------------


class McpSigningKey(SDKModel):
    """One signing key for MCP identity tokens (see ``token_signer.py``).

    ``id`` doubles as the token's ``kid`` (key id) — the same string an
    external MCP's own verifier looks up in its local keystore to know
    which secret to check a given token's signature against.
    """

    id: str = StringField(primary_key=True)  # the kid, e.g. "rag_mcp"
    label: str = StringField(default="")  # human name, e.g. "RAG MCP (Fred, self-hosted)"
    alg: str = StringField(default="HS256")  # "HS256" today; "EdDSA" once that migration lands
    secret: str = StringField()  # shared HMAC secret today; an Ed25519 private key later
    active: bool = BoolField(default=True)  # inactive keys are never used to issue new tokens
    created_at: int = IntField(default=0)  # unix epoch seconds


_MCP_SIGNING_KEYS_PATH = os.getenv(
    "RIGHTS_MCP_SIGNING_KEYS_PATH",
    str(_FALLBACK_DATA_DIR / "mcp-signing-keys.json"),
)

_mcp_signing_keys_table: SDKTable = SDKTable(
    McpSigningKey,
    file_path=_MCP_SIGNING_KEYS_PATH,
    keyring_service="rights-plugin",
)


def create_mcp_signing_key(
    kid: str, secret: str, *, label: str = "", alg: str = "HS256", active: bool = True,
    created_at: int | None = None,
) -> McpSigningKey:
    """Create or update a signing key (upsert by kid, same convention as
    create_role/create_access_right). ``created_at`` defaults to now — only
    overridable so an update through the dashboard/CLI can preserve the
    original creation time instead of resetting it on every edit."""
    existing = get_mcp_signing_key_or_none(kid)
    key = McpSigningKey(
        id=kid, label=label, alg=alg, secret=secret, active=active,
        created_at=created_at if created_at is not None else (existing.created_at if existing else int(time.time())),
    )
    _mcp_signing_keys_table.save(key)
    return key


def get_mcp_signing_key(kid: str) -> McpSigningKey:
    return _mcp_signing_keys_table.get(kid)


def get_mcp_signing_key_or_none(kid: str) -> McpSigningKey | None:
    return _mcp_signing_keys_table.get_or_none(kid)


def delete_mcp_signing_key(kid: str) -> bool:
    return _mcp_signing_keys_table.delete(kid)


def list_mcp_signing_keys() -> list[McpSigningKey]:
    return _mcp_signing_keys_table.list()


def active_mcp_signing_keys() -> list[McpSigningKey]:
    return [k for k in list_mcp_signing_keys() if k.active]


# ---------------------------------------------------------------------------
# Schema migration: AccessRight.role (str) -> AccessRight.roles (list),
# 2026-08-18. Operates on the raw JSON file directly (via the already-public
# FileManager.read_all()/write_all() on _access_rights_table._file), NOT
# through the AccessRight model class — a record still shaped with a bare
# "role" key would otherwise be silently misread the moment AccessRight
# declares "roles" instead: ListField has no way to see the old key, so it
# would just fall back to its empty-list default and every pre-existing
# right would stop matching any role at all. Must run before anything else
# reads _access_rights_table — see the module-level call at the bottom of
# this file.
# ---------------------------------------------------------------------------


def migrate_access_right_role_field() -> int:
    """Rewrite any AccessRight record still shaped ``{"role": "..."}`` into
    ``{"roles": ["..."]}``. Idempotent (a no-op once every record has
    "roles"), safe to call repeatedly. Returns how many records were
    rewritten. Never raises — a corrupt/missing file is reported as 0
    rewritten, not an error, since this must never prevent ``import models``
    from succeeding (see the try/except around its module-level call below).
    """
    try:
        records = _access_rights_table._file.read_all()
    except Exception:
        return 0

    changed = 0
    for record in records:
        if "role" in record and "roles" not in record:
            record["roles"] = [record.pop("role")]
            changed += 1

    if changed:
        _access_rights_table._file.write_all(records)
    return changed


# ---------------------------------------------------------------------------
# Role catalog seed, 2026-08-18. Ensures the two implicit pseudo-roles
# (mirroring identity.ROLE_EVERYONE/ROLE_AUTOMATION — duplicated as literals
# here, not imported, to avoid a models<->identity circular import, same
# reasoning already used for odoo-plugin/w_odoo/rights_bridge.py's own
# ROLE_EVERYONE fallback) always exist in the catalog, and backfills a
# catalog entry for every role string already in use anywhere (RoleBinding
# or AccessRight) so nothing is invisible to the dashboard's pickers after
# an upgrade. Never overwrites an existing entry's label/description.
# ---------------------------------------------------------------------------

_SEED_ROLE_EVERYONE = "everyone"
_SEED_ROLE_AUTOMATION = "automation"


def seed_role_catalog() -> int:
    """Create any missing catalog entry for a role already in use, plus the
    two implicit pseudo-roles. Returns how many entries were created."""
    created = 0

    defaults = {
        _SEED_ROLE_EVERYONE: "Implicit — every resolved identity always holds this role.",
        _SEED_ROLE_AUTOMATION: "Implicit — used when no platform identity resolves at all (cron/system sessions).",
    }
    seen: set[str] = set()
    for role_id, description in defaults.items():
        seen.add(role_id)
        if get_role_or_none(role_id) is None:
            create_role(role_id, label=role_id, description=description)
            created += 1

    for binding in list_role_bindings():
        for role_id in binding.roles:
            if role_id in seen:
                continue
            seen.add(role_id)
            if get_role_or_none(role_id) is None:
                create_role(role_id, label=role_id)
                created += 1

    for right in list_access_rights():
        for role_id in right.roles:
            if role_id in seen:
                continue
            seen.add(role_id)
            if get_role_or_none(role_id) is None:
                create_role(role_id, label=role_id)
                created += 1

    return created


try:
    migrate_access_right_role_field()
except Exception:  # pragma: no cover — must never block `import models` itself
    import logging

    logging.getLogger(__name__).exception(
        "rights-plugin: migrate_access_right_role_field() failed — AccessRight "
        "rows may still be shaped with a legacy 'role' key"
    )

try:
    seed_role_catalog()
except Exception:  # pragma: no cover — must never block `import models` itself
    import logging

    logging.getLogger(__name__).exception("rights-plugin: seed_role_catalog() failed")
