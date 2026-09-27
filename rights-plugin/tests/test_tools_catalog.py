"""tools_catalog.list_hermes_tools — live catalog of Hermes's own registered
tools, backing the dashboard's tool picker for hermes_tool rights.

In this test environment, tools.registry is stubbed with only tool_result
(see tests/conftest.py) — no `registry` singleton — so the "real registry
unreachable" path is exercised for free by every test that doesn't
monkeypatch one in.
"""

import sys
import types

import tools_catalog


def test_returns_empty_list_when_real_registry_unavailable():
    # The stub in conftest.py has no `registry` attribute at all.
    assert tools_catalog.list_hermes_tools() == []


def test_shapes_entries_from_a_fake_registry(monkeypatch):
    class _FakeEntry:
        def __init__(self, toolset, description):
            self.toolset = toolset
            self.description = description

    class _FakeRegistry:
        def get_all_tool_names(self):
            return ["shell_exec", "cronjob"]

        def get_entry(self, name):
            return {
                "shell_exec": _FakeEntry("terminal", "Run a shell command"),
                "cronjob": _FakeEntry("cron", "Unified cron job management"),
            }[name]

    fake_module = types.ModuleType("tools.registry")
    fake_module.registry = _FakeRegistry()
    monkeypatch.setitem(sys.modules, "tools.registry", fake_module)

    result = tools_catalog.list_hermes_tools()
    assert result == [
        {"name": "shell_exec", "toolset": "terminal", "description": "Run a shell command"},
        {"name": "cronjob", "toolset": "cron", "description": "Unified cron job management"},
    ]


def test_missing_entry_still_yields_a_row_with_empty_metadata(monkeypatch):
    class _FakeRegistry:
        def get_all_tool_names(self):
            return ["mystery_tool"]

        def get_entry(self, name):
            return None

    fake_module = types.ModuleType("tools.registry")
    fake_module.registry = _FakeRegistry()
    monkeypatch.setitem(sys.modules, "tools.registry", fake_module)

    result = tools_catalog.list_hermes_tools()
    assert result == [{"name": "mystery_tool", "toolset": "", "description": ""}]


def test_never_raises_when_registry_shape_is_unexpected(monkeypatch):
    class _BrokenRegistry:
        def get_all_tool_names(self):
            raise RuntimeError("boom")

    fake_module = types.ModuleType("tools.registry")
    fake_module.registry = _BrokenRegistry()
    monkeypatch.setitem(sys.modules, "tools.registry", fake_module)

    assert tools_catalog.list_hermes_tools() == []
