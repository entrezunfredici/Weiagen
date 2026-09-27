"""rights_plugin.models — DirectoryEntry storage (list/replace/staleness)."""

import time

from models import directory_last_synced_at, list_directory_entries, replace_directory_entries


def test_replace_directory_entries_creates_rows():
    entries = replace_directory_entries("slack", [
        {"external_user_id": "U1", "display_name": "Fred", "real_name": "Fred M.", "email": "fred@x.com"},
        {"external_user_id": "U2", "display_name": "Ana"},
    ])
    assert {e.external_user_id for e in entries} == {"U1", "U2"}
    assert {e.id for e in entries} == {"slack:U1", "slack:U2"}
    fred = next(e for e in entries if e.external_user_id == "U1")
    assert fred.display_name == "Fred"
    assert fred.email == "fred@x.com"


def test_replace_directory_entries_drops_members_who_left():
    replace_directory_entries("slack", [{"external_user_id": "U1", "display_name": "Fred"}])
    replace_directory_entries("slack", [{"external_user_id": "U2", "display_name": "Ana"}])
    ids = {e.external_user_id for e in list_directory_entries("slack")}
    assert ids == {"U2"}  # U1 is gone — full replace, not a merge


def test_replace_directory_entries_scoped_per_platform():
    replace_directory_entries("slack", [{"external_user_id": "U1", "display_name": "Fred"}])
    replace_directory_entries("telegram", [{"external_user_id": "42", "display_name": "Bob"}])
    assert {e.external_user_id for e in list_directory_entries("slack")} == {"U1"}
    assert {e.external_user_id for e in list_directory_entries("telegram")} == {"42"}
    assert len(list_directory_entries()) == 2  # unfiltered returns every platform


def test_list_directory_entries_empty_by_default():
    assert list_directory_entries("slack") == []


def test_directory_last_synced_at_zero_when_never_synced():
    assert directory_last_synced_at("slack") == 0


def test_directory_last_synced_at_reflects_last_replace():
    before = int(time.time())
    replace_directory_entries("slack", [{"external_user_id": "U1", "display_name": "Fred"}])
    after = int(time.time())
    synced_at = directory_last_synced_at("slack")
    assert before <= synced_at <= after
