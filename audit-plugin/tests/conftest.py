"""Shared pytest fixtures for ``audit-plugin`` tests.

Same pattern as ``rights-plugin/tests/conftest.py`` (see its docstring for
the full rationale): fake the Hermes internals this repo doesn't vendor
(``hermes_constants``, Hermes core's ``tools.registry``,
``hermes_state.SessionDB``), point ``AUDIT_DB_PATH`` at a throwaway file
before any plugin module is imported, and load ``__init__.py`` the way
Hermes's real plugin loader does (``importlib`` with
``submodule_search_locations``).
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

AUDIT_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(AUDIT_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(AUDIT_PLUGIN_DIR))

_DATA_DIR = Path(tempfile.mkdtemp(prefix="audit_plugin_tests_"))
_DB_PATH = _DATA_DIR / "audit.db"
os.environ["AUDIT_DB_PATH"] = str(_DB_PATH)
os.environ.pop("AUDIT_RETENTION_DAYS", None)
os.environ.pop("AUDIT_AGENT_TOOL_ENABLED", None)

# ---------------------------------------------------------------------------
# Hermes stubs
# ---------------------------------------------------------------------------
if "hermes_constants" not in sys.modules:
    _hermes_constants = types.ModuleType("hermes_constants")
    _hermes_constants.get_hermes_home = lambda: _DATA_DIR  # noqa: E731
    sys.modules["hermes_constants"] = _hermes_constants


def _tool_result(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


if "tools" not in sys.modules:
    _tools_pkg = types.ModuleType("tools")
    _tools_registry = types.ModuleType("tools.registry")
    _tools_registry.tool_result = _tool_result
    _tools_pkg.registry = _tools_registry
    sys.modules["tools"] = _tools_pkg
    sys.modules["tools.registry"] = _tools_registry

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


@pytest.fixture(autouse=True)
def _fresh_db(monkeypatch):
    """Give every test an empty audit database and a clean identity cache."""
    import audit_identity
    import audit_store

    for suffix in ("", "-wal", "-shm"):
        Path(str(_DB_PATH) + suffix).unlink(missing_ok=True)
    audit_store._initialized_paths.clear()
    audit_identity.clear_cache()
    monkeypatch.delenv("AUDIT_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("AUDIT_AGENT_TOOL_ENABLED", raising=False)
    yield


@pytest.fixture
def fake_sessions():
    """Populate the fake SessionDB: ``fake_sessions["sid"] = {"source": "slack", "user_id": "U1"}``."""
    _FAKE_SESSIONS.clear()
    yield _FAKE_SESSIONS
    _FAKE_SESSIONS.clear()


@pytest.fixture
def db_path() -> Path:
    """Path of the throwaway SQLite database used by the current test."""
    return _DB_PATH


# ---------------------------------------------------------------------------
# Load the plugin package like Hermes does.
# ---------------------------------------------------------------------------
_PLUGIN_PKG_NAME = "audit_hermes_plugin_under_test"


def _load_submodule(dotted_name: str, file_path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(dotted_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@pytest.fixture(scope="session")
def audit_plugin_pkg():
    """Import ``audit-plugin/__init__.py`` as a real package and return it."""
    if _PLUGIN_PKG_NAME in sys.modules:
        return sys.modules[_PLUGIN_PKG_NAME]
    _load_submodule(f"{_PLUGIN_PKG_NAME}.cli", AUDIT_PLUGIN_DIR / "cli.py")
    _load_submodule(f"{_PLUGIN_PKG_NAME}.tools", AUDIT_PLUGIN_DIR / "tools.py")
    spec = importlib.util.spec_from_file_location(
        _PLUGIN_PKG_NAME,
        AUDIT_PLUGIN_DIR / "__init__.py",
        submodule_search_locations=[str(AUDIT_PLUGIN_DIR)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PLUGIN_PKG_NAME] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@pytest.fixture(scope="session")
def cli_mod(audit_plugin_pkg):
    """The plugin's own ``cli.py``."""
    return sys.modules[f"{_PLUGIN_PKG_NAME}.cli"]


@pytest.fixture(scope="session")
def tools_mod(audit_plugin_pkg):
    """The plugin's own ``tools.py``."""
    return sys.modules[f"{_PLUGIN_PKG_NAME}.tools"]
