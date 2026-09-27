"""w_main.data_manager.file_manager — JSON array storage."""

import pytest

from w_main.data_manager.file_manager import FileManager
from w_main.errors_manager.errors import ServiceError


def test_read_all_on_missing_file_returns_empty_list(tmp_path):
    fm = FileManager(tmp_path / "does-not-exist.json")
    assert fm.read_all() == []


def test_upsert_then_read_one(tmp_path):
    fm = FileManager(tmp_path / "data.json")
    fm.upsert("id", {"id": "a", "value": 1})
    assert fm.read_one("id", "a") == {"id": "a", "value": 1}
    assert fm.read_one("id", "missing") is None


def test_upsert_replaces_existing_record_with_same_pk(tmp_path):
    fm = FileManager(tmp_path / "data.json")
    fm.upsert("id", {"id": "a", "value": 1})
    fm.upsert("id", {"id": "a", "value": 2})
    records = fm.read_all()
    assert len(records) == 1
    assert records[0]["value"] == 2


def test_upsert_appends_distinct_pks(tmp_path):
    fm = FileManager(tmp_path / "data.json")
    fm.upsert("id", {"id": "a"})
    fm.upsert("id", {"id": "b"})
    assert {r["id"] for r in fm.read_all()} == {"a", "b"}


def test_delete_existing_returns_true_and_removes_record(tmp_path):
    fm = FileManager(tmp_path / "data.json")
    fm.upsert("id", {"id": "a"})
    assert fm.delete("id", "a") is True
    assert fm.read_all() == []


def test_delete_missing_returns_false(tmp_path):
    fm = FileManager(tmp_path / "data.json")
    assert fm.delete("id", "missing") is False


def test_write_all_then_read_all_roundtrip(tmp_path):
    fm = FileManager(tmp_path / "data.json")
    records = [{"id": "a"}, {"id": "b"}]
    fm.write_all(records)
    assert fm.read_all() == records


def test_corrupted_json_file_raises_service_error(tmp_path):
    path = tmp_path / "data.json"
    path.write_text("not valid json{{{", encoding="utf-8")
    fm = FileManager(path)
    with pytest.raises(ServiceError):
        fm.read_all()


def test_non_list_json_content_treated_as_empty(tmp_path):
    path = tmp_path / "data.json"
    path.write_text('{"not": "a list"}', encoding="utf-8")
    fm = FileManager(path)
    assert fm.read_all() == []


def test_creates_parent_directories_on_write(tmp_path):
    path = tmp_path / "nested" / "dir" / "data.json"
    fm = FileManager(path)
    fm.upsert("id", {"id": "a"})
    assert path.exists()
