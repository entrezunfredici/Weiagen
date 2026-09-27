"""Shared pytest fixtures for ``rights-plugin`` tests.

Mirrors ``odoo-plugin/tests/conftest.py`` (see that file's own docstring for
the full rationale) with one addition: a fake ``hermes_state.SessionDB``,
needed because ``rights_plugin/identity.py`` resolves an identity from a
``session_id`` via ``hermes_state.SessionDB(read_only=True).get_session(...)``
— a real Hermes internal this repo doesn't vendor (see
``.agents/CONVENTIONS.md``), so tests fake it the same way they fake
``hermes_constants``/Hermes core's ``tools`` package.

Four things this file has to fake, because none of them exist outside a
real Hermes container:

1. ``hermes_constants.get_hermes_home()`` — imported by ``rights_plugin/
   __init__.py`` at module load time.
2. Hermes core's own top-level ``tools`` package (``tools.registry.
   tool_result``) — imported by ``rights_plugin/tools.py`` equivalents.
   Same name-collision hazard documented in ``.agents/CONVENTIONS.md`` for
   odoo-plugin: the plugin's own tool-handling module can never be *named*
   ``tools`` in ``sys.modules``, or it would shadow this stub.
3. ``hermes_state.SessionDB`` — used by ``rights_plugin/identity.py`` to
   resolve ``session_id`` → ``{"source": ..., "user_id": ...}`` inside the
   ``pre_tool_call`` hook context (``pre_llm_call`` gets ``platform``/
   ``sender_id`` directly and never needs this). Confirmed shape verified
   directly against the real Hermes source on ``test-server`` before this plugin
   was designed — see ``.agents/DECISIONS.md``.
4. ``RIGHTS_ROLE_BINDINGS_PATH`` / ``RIGHTS_ACCESS_RIGHTS_PATH`` /
   ``RIGHTS_DIRECTORY_ENTRIES_PATH`` / ``RIGHTS_ROLES_PATH`` /
   ``RIGHTS_MCP_SIGNING_KEYS_PATH`` / ``ODOO_PLUGIN_KEYRING_PATH`` — read
   from the environment at import time by
   ``rights_plugin.models`` / the vendored ``rights_w_main`` copy's
   ``SecretService``. Must be set to a throwaway directory *before* those
   modules are first imported by any test, which is why this file sets them
   at module load time (conftest.py is always imported before test modules
   in the same directory). ``ODOO_PLUGIN_KEYRING_PATH`` keeps its original
   name (not renamed to a ``RIGHTS_*`` equivalent) because the vendored
   ``rights_w_main/data_manager/secret_service.py`` still reads that
   literal string — see that file's header for why it's dead code here
   regardless.

The plugin package itself (``rights_plugin/__init__.py``, and by extension
its ``tools.py``/``cli.py`` once they exist) is loaded the same way Hermes's
real plugin loader loads it (``importlib`` with
``submodule_search_locations``), not hand-imported in isolation — this is
deliberate, same reasoning as odoo-plugin's conftest.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path

import pytest

RIGHTS_PLUGIN_DIR = Path(__file__).resolve().parent.parent

# rights-plugin/ must be on sys.path for `rights_w_main` to be importable
# as a top-level package — mirrors the sys.path bootstrap
# odoo_plugin/__init__.py uses for the same reason (rights_w_main's
# internal imports are absolute, not relative — see .agents/CONVENTIONS.md).
# Named `rights_w_main`, not `w_main`, specifically so it can never
# collide in sys.modules with odoo-plugin's own (differently-vendored)
# `w_main` package when both plugins load in the same Hermes process —
# see .agents/DECISIONS.md.
if str(RIGHTS_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(RIGHTS_PLUGIN_DIR))

# ---------------------------------------------------------------------------
# Throwaway data directory + env vars — set before any
# rights_plugin/rights_w_main module is imported anywhere in the session.
# ---------------------------------------------------------------------------
_DATA_DIR = Path(tempfile.mkdtemp(prefix="rights_plugin_tests_"))
_ROLE_BINDINGS_PATH = _DATA_DIR / "rights-role-bindings.json"
_ACCESS_RIGHTS_PATH = _DATA_DIR / "rights-access-rights.json"
_DIRECTORY_ENTRIES_PATH = _DATA_DIR / "rights-directory-entries.json"
_ROLES_PATH = _DATA_DIR / "rights-roles.json"
_MCP_SIGNING_KEYS_PATH = _DATA_DIR / "rights-mcp-signing-keys.json"
_KEYRING_PATH = _DATA_DIR / "rights-keyring.json"  # unused (no SecretField), set for parity only

os.environ["RIGHTS_ROLE_BINDINGS_PATH"] = str(_ROLE_BINDINGS_PATH)
os.environ["RIGHTS_ACCESS_RIGHTS_PATH"] = str(_ACCESS_RIGHTS_PATH)
os.environ["RIGHTS_DIRECTORY_ENTRIES_PATH"] = str(_DIRECTORY_ENTRIES_PATH)
os.environ["RIGHTS_ROLES_PATH"] = str(_ROLES_PATH)
os.environ["RIGHTS_MCP_SIGNING_KEYS_PATH"] = str(_MCP_SIGNING_KEYS_PATH)
os.environ["ODOO_PLUGIN_KEYRING_PATH"] = str(_KEYRING_PATH)
os.environ.pop("ODOO_PLUGIN_ENCRYPTION_KEY", None)
# Never actually called in tests (SLACK_BOT_TOKEN unset by default) unless a
# test explicitly monkeypatches it in — a stray real token in the test
# runner's environment must never cause a real network call.
os.environ.pop("SLACK_BOT_TOKEN", None)


@pytest.fixture(autouse=True)
def _reset_plugin_data_files():
    """Truncate role-bindings/access-rights/keyring JSON files before every test.

    The module-level ``SDKTable`` singletons in ``rights_plugin.models`` are
    shared across the whole test session (Python only imports a module
    once) — this fixture is what keeps individual tests from seeing each
    other's data.
    """
    for path in (
        _ROLE_BINDINGS_PATH, _ACCESS_RIGHTS_PATH, _DIRECTORY_ENTRIES_PATH,
        _ROLES_PATH, _MCP_SIGNING_KEYS_PATH, _KEYRING_PATH,
    ):
        path.write_text("[]" if path != _KEYRING_PATH else "{}", encoding="utf-8")
    os.environ.pop("ODOO_PLUGIN_ENCRYPTION_KEY", None)
    os.environ.pop("SLACK_BOT_TOKEN", None)
    yield


# ---------------------------------------------------------------------------
# Stub hermes_constants (rights_plugin/__init__.py: `from hermes_constants
# import get_hermes_home`).
# ---------------------------------------------------------------------------
if "hermes_constants" not in sys.modules:
    _hermes_constants = types.ModuleType("hermes_constants")
    _hermes_constants.get_hermes_home = lambda: _DATA_DIR  # noqa: E731
    sys.modules["hermes_constants"] = _hermes_constants


# ---------------------------------------------------------------------------
# Stub Hermes core's native `tools` package (rights_plugin/tools.py: `from
# tools.registry import tool_result`).
# ---------------------------------------------------------------------------
def _tool_result(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


if "tools" not in sys.modules:
    _tools_pkg = types.ModuleType("tools")
    _tools_registry = types.ModuleType("tools.registry")
    _tools_registry.tool_result = _tool_result
    _tools_pkg.registry = _tools_registry
    sys.modules["tools"] = _tools_pkg
    sys.modules["tools.registry"] = _tools_registry


# ---------------------------------------------------------------------------
# Stub hermes_state.SessionDB (rights_plugin/identity.py: `from hermes_state
# import SessionDB`). A tiny in-memory fake keyed by session_id — tests
# populate it via the `fake_sessions` fixture below rather than touching
# module state directly.
# ---------------------------------------------------------------------------
_FAKE_SESSIONS: dict[str, dict] = {}


class _FakeSessionDB:
    def __init__(self, db_path=None, read_only: bool = False) -> None:  # noqa: ARG002
        pass

    def get_session(self, session_id: str) -> dict | None:
        return _FAKE_SESSIONS.get(session_id)


if "hermes_state" not in sys.modules:
    _hermes_state = types.ModuleType("hermes_state")
    _hermes_state.SessionDB = _FakeSessionDB
    sys.modules["hermes_state"] = _hermes_state


@pytest.fixture
def fake_sessions():
    """Populate the fake SessionDB for one test: `fake_sessions["sid"] = {"source": "slack", "user_id": "U1"}`."""
    _FAKE_SESSIONS.clear()
    yield _FAKE_SESSIONS
    _FAKE_SESSIONS.clear()


# ---------------------------------------------------------------------------
# Load the plugin package (__init__.py + its relative submodules cli.py/
# engine.py/identity.py/models.py) the same way Hermes's real loader does:
# importlib with submodule_search_locations, not `import rights_plugin` (the
# directory name has a hyphen, so that spelling isn't even valid Python).
# ---------------------------------------------------------------------------
_PLUGIN_PKG_NAME = "rights_hermes_plugin_under_test"


def _load_submodule(dotted_name: str, file_path: Path) -> types.ModuleType:
    """Load *file_path* directly and register it under *dotted_name*.

    Pre-registering it in ``sys.modules`` means that when ``__init__.py``'s
    own ``from .cli import ...`` runs, Python's import system finds the
    module already loaded and returns it straight from ``sys.modules``
    *without* consulting ``sys.meta_path`` again — see odoo-plugin's
    conftest.py for the pytest-assertion-rewrite hazard this avoids.
    """
    spec = importlib.util.spec_from_file_location(dotted_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@pytest.fixture(scope="session")
def rights_plugin_pkg():
    """Import ``rights_plugin/__init__.py`` as a real package and return it."""
    if _PLUGIN_PKG_NAME in sys.modules:
        return sys.modules[_PLUGIN_PKG_NAME]

    _load_submodule(f"{_PLUGIN_PKG_NAME}.cli", RIGHTS_PLUGIN_DIR / "cli.py")

    spec = importlib.util.spec_from_file_location(
        _PLUGIN_PKG_NAME,
        RIGHTS_PLUGIN_DIR / "__init__.py",
        submodule_search_locations=[str(RIGHTS_PLUGIN_DIR)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PLUGIN_PKG_NAME] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@pytest.fixture(scope="session")
def cli_mod(rights_plugin_pkg):
    """The plugin's own ``cli.py``, loaded as ``rights_hermes_plugin_under_test.cli``."""
    return sys.modules[f"{_PLUGIN_PKG_NAME}.cli"]
