"""Sanity check that the plugin-loading machinery in conftest.py actually works."""


def test_plugin_package_loads(odoo_plugin_pkg):
    assert hasattr(odoo_plugin_pkg, "register")
    assert hasattr(odoo_plugin_pkg, "_pre_tool_call")


def test_tools_module_loads_and_sees_native_tools_stub(tools_mod):
    assert len(tools_mod.ALL_TOOLS) > 0
    result = tools_mod._run(lambda: {"ok": True})
    assert result == '{"ok": true}'


def test_cli_module_loads(cli_mod):
    assert hasattr(cli_mod, "odoo_command")
    assert hasattr(cli_mod, "register_cli")
