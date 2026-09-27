"""Shared pytest fixtures for ``odoo-plugin`` tests.

Four things this file has to fake, because none of them exist outside a
real Hermes container:

1. ``hermes_constants.get_hermes_home()`` — imported by ``odoo_plugin/
   __init__.py`` at module load time.
2. Hermes core's own top-level ``tools`` package (``tools.registry.
   tool_result``) — imported by ``odoo_plugin/tools.py``. This is the exact
   name collision documented in ``.agents/CONVENTIONS.md`` ("un import
   absolu percute le paquet ``tools`` natif de Hermes"): the plugin's own
   ``tools.py`` can never be *named* ``tools`` in ``sys.modules``, or it
   would shadow this stub (and vice versa) — see how it's loaded below.
3. ``hermes_state.SessionDB`` — transitively imported via
   ``w_odoo.rights_bridge`` -> ``rights_plugin_api`` ->
   ``rights_plugin/identity.py``, which resolves a ``session_id`` to a
   platform/user via ``SessionDB(read_only=True).get_session(...)``. Faked
   the same way rights-plugin's own tests/conftest.py fakes it (see that
   file) — kept independent rather than shared, since the two test suites
   run as fully separate pytest processes (different CI jobs).
4. ``ODOO_PROFILES_FILE_PATH`` / ``ODOO_RIGHTS_PATH`` /
   ``ODOO_PLUGIN_KEYRING_PATH`` — read from the environment at import time
   by ``w_odoo.odoo_profile`` / ``w_main``'s ``SecretService``.
   ``ODOO_RIGHTS_PATH`` no longer backs a live model in this plugin (rights
   moved to rights-plugin) but is kept as a legacy-migration source path
   fixture for tests that exercise that path. Must be set to a throwaway
   directory *before* those modules are first imported by any test, which
   is why this file sets them at module load time (conftest.py is always
   imported before test modules in the same directory).

The plugin package itself (``odoo_plugin/__init__.py``, and by extension its
``tools.py``/``cli.py``) is loaded the same way Hermes's real plugin loader
loads it (``importlib`` with ``submodule_search_locations``, see
``odoo_hermes_plugin`` fixture below) rather than hand-importing ``tools.py``
in isolation — this is deliberate: it means the test suite would fail loudly
if the tools/cli-vs-native-tools import collision bug ever came back.
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

ODOO_PLUGIN_DIR = Path(__file__).resolve().parent.parent

# odoo-plugin/ must be on sys.path for `w_main`/`w_odoo` to be
# importable as top-level packages — mirrors the sys.path bootstrap in
# odoo_plugin/__init__.py (see the comment there for why).
if str(ODOO_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(ODOO_PLUGIN_DIR))

# ---------------------------------------------------------------------------
# Throwaway data directory + env vars — set before any w_odoo/w_main
# module is imported anywhere in the session.
# ---------------------------------------------------------------------------
_DATA_DIR = Path(tempfile.mkdtemp(prefix="odoo_plugin_tests_"))
_PROFILES_PATH = _DATA_DIR / "odoo-profiles.json"
_RIGHTS_PATH = _DATA_DIR / "odoo-rights.json"  # legacy migration source fixture only, see below
_KEYRING_PATH = _DATA_DIR / "odoo-keyring.json"

os.environ["ODOO_PROFILES_FILE_PATH"] = str(_PROFILES_PATH)
os.environ["ODOO_RIGHTS_PATH"] = str(_RIGHTS_PATH)
os.environ["ODOO_PLUGIN_KEYRING_PATH"] = str(_KEYRING_PATH)
os.environ.pop("ODOO_PLUGIN_ENCRYPTION_KEY", None)

# rights-plugin's own data files — set here too since w_odoo.rights_bridge
# transitively imports rights_plugin_api -> models.py, which builds its
# SDKTables from these env vars at import time, same as ODOO_* above.
_RIGHTS_ROLE_BINDINGS_PATH = _DATA_DIR / "rights-role-bindings.json"
_RIGHTS_ACCESS_RIGHTS_PATH = _DATA_DIR / "rights-access-rights.json"
os.environ["RIGHTS_ROLE_BINDINGS_PATH"] = str(_RIGHTS_ROLE_BINDINGS_PATH)
os.environ["RIGHTS_ACCESS_RIGHTS_PATH"] = str(_RIGHTS_ACCESS_RIGHTS_PATH)


@pytest.fixture(autouse=True)
def _reset_plugin_data_files():
    """Truncate profiles/rights/keyring JSON files before every test.

    The module-level ``_table``/``SecretService`` singletons in
    ``w_odoo.odoo_profile`` and rights-plugin's ``models.py`` are shared
    across the whole test session (Python only imports a module once) —
    this fixture is what keeps individual tests from seeing each other's
    data.
    """
    for path in (
        _PROFILES_PATH, _RIGHTS_PATH, _RIGHTS_ROLE_BINDINGS_PATH, _RIGHTS_ACCESS_RIGHTS_PATH,
    ):
        path.write_text("[]", encoding="utf-8")
    _KEYRING_PATH.write_text("{}", encoding="utf-8")
    os.environ.pop("ODOO_PLUGIN_ENCRYPTION_KEY", None)
    yield


# ---------------------------------------------------------------------------
# Stub hermes_constants (odoo_plugin/__init__.py: `from hermes_constants
# import get_hermes_home`).
# ---------------------------------------------------------------------------
if "hermes_constants" not in sys.modules:
    _hermes_constants = types.ModuleType("hermes_constants")
    _hermes_constants.get_hermes_home = lambda: _DATA_DIR  # noqa: E731
    sys.modules["hermes_constants"] = _hermes_constants


# ---------------------------------------------------------------------------
# Stub Hermes core's native `tools` package (odoo_plugin/tools.py: `from
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
# Stub hermes_state.SessionDB (transitively imported via
# w_odoo.rights_bridge -> rights_plugin_api -> rights_plugin/identity.py).
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
# Load the plugin package (__init__.py + its relative submodules tools.py/
# cli.py) the same way Hermes's real loader does: importlib with
# submodule_search_locations, not `import odoo_plugin` (the directory name
# has a hyphen, so that spelling isn't even valid Python).
# ---------------------------------------------------------------------------
_PLUGIN_PKG_NAME = "odoo_hermes_plugin_under_test"


def _load_submodule(dotted_name: str, file_path: Path) -> types.ModuleType:
    """Load *file_path* directly and register it under *dotted_name*.

    Pre-registering it in ``sys.modules`` means that when ``__init__.py``'s
    own ``from .cli import ...`` / ``from .tools import ...`` run, Python's
    import system finds the module already loaded and returns it straight
    from ``sys.modules`` *without* consulting ``sys.meta_path`` again. That
    matters under pytest specifically: pytest's assertion-rewrite import
    hook otherwise intercepts that nested relative import and re-executes it
    in a context where ``__package__`` isn't set the way a genuine package
    submodule import would set it, raising ``ImportError: attempted
    relative import with no known parent package`` — reproducible only when
    running under pytest, not in a plain interpreter (confirmed while
    writing this fixture).
    """
    spec = importlib.util.spec_from_file_location(dotted_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@pytest.fixture(scope="session")
def odoo_plugin_pkg():
    """Import ``odoo_plugin/__init__.py`` as a real package and return it."""
    if _PLUGIN_PKG_NAME in sys.modules:
        return sys.modules[_PLUGIN_PKG_NAME]

    _load_submodule(f"{_PLUGIN_PKG_NAME}.cli", ODOO_PLUGIN_DIR / "cli.py")
    _load_submodule(f"{_PLUGIN_PKG_NAME}.tools", ODOO_PLUGIN_DIR / "tools.py")

    spec = importlib.util.spec_from_file_location(
        _PLUGIN_PKG_NAME,
        ODOO_PLUGIN_DIR / "__init__.py",
        submodule_search_locations=[str(ODOO_PLUGIN_DIR)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PLUGIN_PKG_NAME] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@pytest.fixture(scope="session")
def tools_mod(odoo_plugin_pkg):
    """The plugin's own ``tools.py``, loaded as ``odoo_hermes_plugin_under_test.tools``."""
    return sys.modules[f"{_PLUGIN_PKG_NAME}.tools"]


@pytest.fixture(scope="session")
def cli_mod(odoo_plugin_pkg):
    """The plugin's own ``cli.py``, loaded as ``odoo_hermes_plugin_under_test.cli``."""
    return sys.modules[f"{_PLUGIN_PKG_NAME}.cli"]


# ---------------------------------------------------------------------------
# Fake Odoo transport — stands in for w_odoo.odoo_client.OdooClient so
# executor tests never need the real `odoolib` package or a network call.
# ---------------------------------------------------------------------------
class FakeOdooClient:
    """Records calls and returns canned data; swap in for OdooClient in tests."""

    def __init__(self, schema: dict | None = None, records: list[dict] | None = None, **_conn_kwargs) -> None:
        self.schema = schema or {}
        self.records = records if records is not None else []
        self.calls: list[tuple[str, tuple, dict]] = []
        self._next_create_id = 100

    def get_model(self, model_name: str):
        self.calls.append(("get_model", (model_name,), {}))
        return self

    def get_model_schema(self, model: str) -> dict:
        self.calls.append(("get_model_schema", (model,), {}))
        return self.schema

    def get(self, model_name, domain, fields, limit=None):
        self.calls.append(("get", (model_name, domain, fields, limit), {}))
        return self.records

    def post(self, model_name, values):
        self.calls.append(("post", (model_name, dict(values)), {}))
        self._next_create_id += 1
        return self._next_create_id

    def put(self, model_name, object_ids, values):
        self.calls.append(("put", (model_name, list(object_ids), dict(values)), {}))
        return True

    def delete(self, model_name, object_ids):
        self.calls.append(("delete", (model_name, list(object_ids)), {}))
        return True

    # search_read is called on `client.get_model("ir.model")` result in
    # _list_models — since get_model() returns self here, expose it too.
    def search_read(self, domain, fields, order=None):
        self.calls.append(("search_read", (domain, fields, order), {}))
        return self.records


@pytest.fixture
def fake_odoo_client():
    return FakeOdooClient()
