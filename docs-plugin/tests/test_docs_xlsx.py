"""w_docs.xlsx_generator / xlsx_reader — create then read back a real .xlsx."""

from w_docs.xlsx_generator import create_xlsx
from w_docs.xlsx_reader import read_xlsx


def test_create_and_read_roundtrip(tmp_path):
    path = tmp_path / "out.xlsx"
    result = create_xlsx(str(path), [
        {
            "name": "Sheet1",
            "headers": ["Name", "Amount"],
            "rows": [["Alice", 10], ["Bob", 20]],
        },
    ])
    assert result["ok"] is True
    assert path.exists()

    read = read_xlsx(str(path))
    assert read["ok"] is True
    assert len(read["sheets"]) == 1
    sheet = read["sheets"][0]
    assert sheet["name"] == "Sheet1"
    assert sheet["rows"][0] == ["Name", "Amount"]
    assert sheet["rows"][1] == ["Alice", "10"]  # values_only cells stringified by the reader


def test_create_with_no_sheets_falls_back_to_default_sheet(tmp_path):
    path = tmp_path / "out.xlsx"
    create_xlsx(str(path), [])
    read = read_xlsx(str(path))
    assert read["sheets"][0]["name"] == "Sheet1"


def test_read_sheet_names_filter(tmp_path):
    path = tmp_path / "out.xlsx"
    create_xlsx(str(path), [
        {"name": "A", "rows": [["x"]]},
        {"name": "B", "rows": [["y"]]},
    ])
    read = read_xlsx(str(path), sheet_names=["B"])
    assert [s["name"] for s in read["sheets"]] == ["B"]


def test_create_multiple_sheets(tmp_path):
    path = tmp_path / "out.xlsx"
    create_xlsx(str(path), [
        {"name": "Sheet1", "headers": ["A"], "rows": [[1]]},
        {"name": "Sheet2", "headers": ["B"], "rows": [[2]]},
    ])
    read = read_xlsx(str(path))
    assert {s["name"] for s in read["sheets"]} == {"Sheet1", "Sheet2"}


def test_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "dir" / "out.xlsx"
    create_xlsx(str(path), [{"name": "Sheet1", "rows": [["x"]]}])
    assert path.exists()
