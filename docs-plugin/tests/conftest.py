"""Shared pytest fixtures for ``docs-plugin`` tests.

Same pattern as the other plugins' ``tests/conftest.py``: fake the Hermes
internals this repo doesn't vendor (``hermes_constants.get_hermes_dir``,
Hermes core's ``tools.registry``) and load ``__init__.py`` the way Hermes's
plugin loader does. ``HERMES_HOME`` is a fresh temp dir per test, so the
default output directory (``<home>/cache/documents/generated``) never
leaks between tests.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

DOCS_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(DOCS_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(DOCS_PLUGIN_DIR))

_STATE = {"home": Path("/nonexistent")}


def _get_hermes_dir(new_subpath: str, old_name: str) -> Path:  # noqa: ARG001
    return _STATE["home"] / new_subpath


if "hermes_constants" not in sys.modules:
    _hermes_constants = types.ModuleType("hermes_constants")
    _hermes_constants.get_hermes_dir = _get_hermes_dir
    _hermes_constants.get_hermes_home = lambda: _STATE["home"]  # noqa: E731
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


@pytest.fixture(autouse=True)
def hermes_home(tmp_path, monkeypatch):
    """A throwaway HERMES_HOME for each test; also clears DOCS_OUTPUT_DIRS."""
    home = tmp_path / "hermes_home"
    home.mkdir()
    _STATE["home"] = home
    monkeypatch.delenv("DOCS_OUTPUT_DIRS", raising=False)
    return home


@pytest.fixture
def default_dir(hermes_home) -> Path:
    """The default output directory for the current test."""
    return (hermes_home / "cache" / "documents" / "generated").resolve()


_PLUGIN_PKG_NAME = "docs_hermes_plugin_under_test"


@pytest.fixture(scope="session")
def docs_plugin_pkg():
    """Import ``docs-plugin/__init__.py`` as a real package and return it."""
    if _PLUGIN_PKG_NAME in sys.modules:
        return sys.modules[_PLUGIN_PKG_NAME]
    tools_spec = importlib.util.spec_from_file_location(f"{_PLUGIN_PKG_NAME}.tools", DOCS_PLUGIN_DIR / "tools.py")
    tools_module = importlib.util.module_from_spec(tools_spec)
    sys.modules[f"{_PLUGIN_PKG_NAME}.tools"] = tools_module
    tools_spec.loader.exec_module(tools_module)  # type: ignore[union-attr]

    spec = importlib.util.spec_from_file_location(
        _PLUGIN_PKG_NAME, DOCS_PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(DOCS_PLUGIN_DIR)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PLUGIN_PKG_NAME] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@pytest.fixture(scope="session")
def tools_mod(docs_plugin_pkg):
    """The plugin's own ``tools.py``."""
    return sys.modules[f"{_PLUGIN_PKG_NAME}.tools"]
