"""w_docs.pptx_generator / pptx_reader — create then read back a real .pptx."""

from w_docs.pptx_generator import create_pptx
from w_docs.pptx_reader import read_pptx


def test_title_slide_roundtrip(tmp_path):
    path = tmp_path / "out.pptx"
    result = create_pptx(str(path), [
        {"layout": "title", "title": "My Deck", "subtitle": "A subtitle"},
    ])
    assert result["ok"] is True
    assert result["slides_count"] == 1

    read = read_pptx(str(path))
    assert read["ok"] is True
    assert read["slide_count"] == 1
    assert read["slides"][0]["title"] == "My Deck"
    assert "A subtitle" in read["slides"][0]["text"]


def test_content_slide_bullets(tmp_path):
    path = tmp_path / "out.pptx"
    create_pptx(str(path), [
        {"layout": "content", "title": "Agenda", "content": ["Point one", "Point two"]},
    ])
    read = read_pptx(str(path))
    slide = read["slides"][0]
    assert slide["title"] == "Agenda"
    assert "Point one" in slide["text"]
    assert "Point two" in slide["text"]


def test_two_column_slide(tmp_path):
    path = tmp_path / "out.pptx"
    create_pptx(str(path), [
        {"layout": "two_column", "title": "Comparison", "left": ["Pro A"], "right": ["Con B"]},
    ])
    read = read_pptx(str(path))
    slide = read["slides"][0]
    assert "Pro A" in slide["text"]
    assert "Con B" in slide["text"]


def test_blank_slide_with_body_text(tmp_path):
    path = tmp_path / "out.pptx"
    create_pptx(str(path), [{"layout": "blank", "body": "Free-form text here"}])
    read = read_pptx(str(path))
    assert "Free-form text here" in read["slides"][0]["text"]


def test_multiple_slides_ordered(tmp_path):
    path = tmp_path / "out.pptx"
    create_pptx(str(path), [
        {"layout": "content", "title": "First"},
        {"layout": "content", "title": "Second"},
    ])
    read = read_pptx(str(path))
    assert [s["title"] for s in read["slides"]] == ["First", "Second"]
    assert [s["slide"] for s in read["slides"]] == [1, 2]


def test_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "dir" / "out.pptx"
    create_pptx(str(path), [{"layout": "blank", "body": "x"}])
    assert path.exists()
