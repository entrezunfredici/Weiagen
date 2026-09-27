"""docs_paths.py — output path policy and MEDIA tag."""

import os

import pytest

from docs_paths import OutputPathError, allowed_output_roots, media_tag, resolve_output_path


def test_empty_output_path_autonames_in_default_dir(default_dir):
    path = resolve_output_path(None, extension=".xlsx", kind="spreadsheet")
    assert path.parent == default_dir
    assert path.name.startswith("spreadsheet-") and path.suffix == ".xlsx"
    assert resolve_output_path("  ", extension=".xlsx", kind="spreadsheet").parent == default_dir


def test_two_autonames_differ():
    a = resolve_output_path(None, extension=".docx", kind="document")
    b = resolve_output_path(None, extension=".docx", kind="document")
    assert a != b


def test_bare_filename_goes_to_default_dir(default_dir):
    assert resolve_output_path("ventes.xlsx", extension=".xlsx", kind="s") == default_dir / "ventes.xlsx"


def test_extension_is_appended_when_missing(default_dir):
    assert resolve_output_path("rapport", extension=".docx", kind="d") == default_dir / "rapport.docx"


def test_extension_case_insensitive(default_dir):
    assert resolve_output_path("A.XLSX", extension=".xlsx", kind="s") == default_dir / "A.xlsx"


def test_wrong_extension_rejected():
    with pytest.raises(OutputPathError, match="must end with '.xlsx'"):
        resolve_output_path("config.yaml", extension=".xlsx", kind="s")


def test_relative_subdir_kept(default_dir):
    assert resolve_output_path("q3/bilan.pptx", extension=".pptx", kind="p") == default_dir / "q3" / "bilan.pptx"


def test_relative_parent_traversal_rejected():
    with pytest.raises(OutputPathError, match=r"\.\."):
        resolve_output_path("../../config.xlsx", extension=".xlsx", kind="s")


def test_unsafe_characters_sanitized_but_accents_kept(default_dir):
    path = resolve_output_path("Rapport février: <final>.xlsx", extension=".xlsx", kind="s")
    assert path == default_dir / "Rapport février_ _final_.xlsx"


def test_absolute_path_inside_default_dir_accepted(default_dir):
    target = default_dir / "x.xlsx"
    assert resolve_output_path(str(target), extension=".xlsx", kind="s") == target


def test_absolute_path_outside_rejected(tmp_path):
    with pytest.raises(OutputPathError, match="outside the allowed output directories"):
        resolve_output_path(str(tmp_path / "elsewhere" / "x.xlsx"), extension=".xlsx", kind="s")


def test_legacy_workspace_path_rejected():
    # The old skill examples used /workspace/...: now refused with a hint.
    with pytest.raises(OutputPathError, match="Omit output_path"):
        resolve_output_path("/workspace/ventes.xlsx", extension=".xlsx", kind="s")


def test_extra_roots_from_env(tmp_path, monkeypatch):
    extra = tmp_path / "shared"
    monkeypatch.setenv("DOCS_OUTPUT_DIRS", f"relative/ignored,{extra}")
    assert extra.resolve() in allowed_output_roots()
    assert resolve_output_path(str(extra / "a.docx"), extension=".docx", kind="d") == extra.resolve() / "a.docx"
    assert len(allowed_output_roots()) == 2


def test_symlink_escaping_the_root_rejected(default_dir, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    default_dir.mkdir(parents=True)
    os.symlink(outside, default_dir / "link")
    with pytest.raises(OutputPathError):
        resolve_output_path("link/x.xlsx", extension=".xlsx", kind="s")


def test_media_tag():
    assert media_tag("/a/b.xlsx") == "MEDIA:/a/b.xlsx"
