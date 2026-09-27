"""w_docs.docx_generator / docx_reader — create then read back a real .docx."""

from w_docs.docx_generator import create_docx
from w_docs.docx_reader import read_docx


def test_create_and_read_heading_and_paragraph(tmp_path):
    path = tmp_path / "out.docx"
    result = create_docx(str(path), [
        {"type": "heading", "level": 2, "text": "Section One"},
        {"type": "paragraph", "text": "Some body text."},
    ])
    assert result["ok"] is True
    assert path.exists()

    read = read_docx(str(path))
    assert read["ok"] is True
    blocks = read["content"]
    assert {"type": "heading", "level": 2, "text": "Section One"} in blocks
    assert {"type": "paragraph", "text": "Some body text."} in blocks


def test_bullet_and_numbered_lists(tmp_path):
    path = tmp_path / "out.docx"
    create_docx(str(path), [
        {"type": "bullet_list", "items": ["one", "two"]},
        {"type": "numbered_list", "items": ["first"]},
    ])
    read = read_docx(str(path))
    types_and_text = [(b["type"], b["text"]) for b in read["content"]]
    assert ("bullet", "one") in types_and_text
    assert ("bullet", "two") in types_and_text
    assert ("numbered", "first") in types_and_text


def test_table_roundtrip(tmp_path):
    path = tmp_path / "out.docx"
    create_docx(str(path), [
        {"type": "table", "headers": ["Name", "Age"], "rows": [["Alice", "30"], ["Bob", "40"]]},
    ])
    read = read_docx(str(path))
    tables = [b for b in read["content"] if b["type"] == "table"]
    assert len(tables) == 1
    assert tables[0]["headers"] == ["Name", "Age"]
    assert tables[0]["rows"] == [["Alice", "30"], ["Bob", "40"]]


def test_page_break_does_not_crash(tmp_path):
    path = tmp_path / "out.docx"
    result = create_docx(str(path), [
        {"type": "paragraph", "text": "Before"},
        {"type": "page_break"},
        {"type": "paragraph", "text": "After"},
    ])
    assert result["ok"] is True
    read = read_docx(str(path))
    texts = [b["text"] for b in read["content"] if b["type"] == "paragraph"]
    assert texts == ["Before", "After"]


def test_empty_paragraphs_are_skipped_by_reader(tmp_path):
    path = tmp_path / "out.docx"
    create_docx(str(path), [
        {"type": "paragraph", "text": "Real text"},
        {"type": "paragraph", "text": ""},
    ])
    read = read_docx(str(path))
    assert len(read["content"]) == 1


def test_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "dir" / "out.docx"
    create_docx(str(path), [{"type": "paragraph", "text": "x"}])
    assert path.exists()
