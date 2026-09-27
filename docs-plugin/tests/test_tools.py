"""tools.py handlers + register() — end to end on real files."""

import json


class _FakeCtx:
    def __init__(self):
        self.tools = []

    def register_tool(self, **kw):
        self.tools.append((kw["name"], kw["toolset"]))


def _call(handler, args):
    return json.loads(handler(args, task_id="t", session_id="s"))


def test_register_keeps_names_and_toolset(docs_plugin_pkg):
    ctx = _FakeCtx()
    docs_plugin_pkg.register(ctx)
    assert ctx.tools == [
        ("docs_create_xlsx", "docs"), ("docs_create_docx", "docs"), ("docs_create_pptx", "docs"),
        ("docs_read_xlsx", "docs"), ("docs_read_docx", "docs"), ("docs_read_pptx", "docs"),
    ]


def test_schemas_output_path_optional(tools_mod):
    for schema in (tools_mod.DOCS_CREATE_XLSX_SCHEMA, tools_mod.DOCS_CREATE_DOCX_SCHEMA, tools_mod.DOCS_CREATE_PPTX_SCHEMA):
        assert "output_path" in schema["parameters"]["properties"]
        assert "output_path" not in schema["parameters"]["required"]


def test_create_xlsx_default_location_and_media(tools_mod, default_dir):
    out = _call(tools_mod.handle_docs_create_xlsx, {"sheets": [{"name": "S", "headers": ["a"], "rows": [[1]]}]})
    assert out["ok"] is True
    assert out["path"].startswith(str(default_dir))
    assert out["media"] == f"MEDIA:{out['path']}"
    assert "MEDIA" in out["delivery"]
    read = _call(tools_mod.handle_docs_read_xlsx, {"input_path": out["path"]})
    assert read["sheets"][0]["rows"][0] == ["a"]


def test_create_docx_with_filename_then_read(tools_mod, default_dir):
    out = _call(tools_mod.handle_docs_create_docx, {
        "output_path": "compte-rendu",
        "title": "CR",
        "content": [{"type": "paragraph", "text": "Bonjour"}],
    })
    assert out["path"] == str(default_dir / "compte-rendu.docx")
    read = _call(tools_mod.handle_docs_read_docx, {"input_path": out["path"]})
    assert {"type": "paragraph", "text": "Bonjour"} in read["content"]


def test_create_pptx_then_read(tools_mod):
    out = _call(tools_mod.handle_docs_create_pptx, {"slides": [{"layout": "title", "title": "Hello", "subtitle": "x"}]})
    assert out["ok"] is True
    read = _call(tools_mod.handle_docs_read_pptx, {"input_path": out["path"]})
    assert read["slides"][0]["title"] == "Hello"


def test_outside_path_is_validation_error(tools_mod, tmp_path):
    out = _call(tools_mod.handle_docs_create_xlsx, {"output_path": str(tmp_path / "x.xlsx"), "sheets": []})
    assert out["ok"] is False
    assert out["error"]["code"] == "VALIDATION_ERROR"
    assert not (tmp_path / "x.xlsx").exists()


def test_missing_required_argument_is_validation_error(tools_mod):
    for handler, args in (
        (tools_mod.handle_docs_create_xlsx, {}),
        (tools_mod.handle_docs_create_docx, {}),
        (tools_mod.handle_docs_create_pptx, {}),
        (tools_mod.handle_docs_read_xlsx, {}),
    ):
        out = _call(handler, args)
        assert out["error"]["code"] == "VALIDATION_ERROR", handler.__name__


def test_read_missing_file_is_unhandled_error(tools_mod, tmp_path):
    out = _call(tools_mod.handle_docs_read_docx, {"input_path": str(tmp_path / "nope.docx")})
    assert out["ok"] is False
    assert out["error"]["code"] == "UNHANDLED_ERROR"
