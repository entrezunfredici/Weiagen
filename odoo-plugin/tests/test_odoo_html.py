"""w_odoo.odoo_html — plain-text -> HTML normalization for Odoo html fields."""

from w_odoo.odoo_html import looks_like_html, normalize_html_values, text_to_html


def test_looks_like_html_true_for_recognized_tags():
    assert looks_like_html("<p>hello</p>") is True
    assert looks_like_html("some <b>bold</b> text") is True


def test_looks_like_html_false_for_plain_text():
    assert looks_like_html("plain text, no markup") is False
    assert looks_like_html("1 < 2 and 3 > 2") is False  # not a recognized tag name


def test_text_to_html_empty_string_passthrough():
    assert text_to_html("") == ""


def test_text_to_html_single_line():
    assert text_to_html("hello world") == "<p>hello world</p>"


def test_text_to_html_single_newline_becomes_br():
    assert text_to_html("line1\nline2") == "<p>line1<br/>line2</p>"


def test_text_to_html_blank_line_separated_becomes_paragraphs():
    result = text_to_html("para one\n\npara two")
    assert result == "<p>para one</p><p>para two</p>"


def test_text_to_html_escapes_special_characters():
    result = text_to_html("<script>alert(1)</script>")
    # This string DOES contain a recognized tag-looking prefix? "<script"
    # isn't in the recognized tag list, so it's treated as plain text and
    # escaped rather than passed through verbatim.
    assert "&lt;script&gt;" in result
    assert "<script>" not in result


def test_text_to_html_leaves_real_html_untouched():
    value = "<p>Already <b>styled</b></p>"
    assert text_to_html(value) == value


def test_normalize_html_values_only_touches_named_fields():
    values = {"description": "line1\nline2", "name": "line1\nline2", "count": 5}
    result = normalize_html_values(values, {"description"})
    assert result["description"] == "<p>line1<br/>line2</p>"
    assert result["name"] == "line1\nline2"  # untouched, not in html_field_names
    assert result["count"] == 5  # non-string, untouched


def test_normalize_html_values_empty_field_set_returns_input_unchanged():
    values = {"description": "line1\nline2"}
    assert normalize_html_values(values, set()) is values


def test_normalize_html_values_does_not_mutate_input():
    values = {"description": "line1\nline2"}
    normalize_html_values(values, {"description"})
    assert values["description"] == "line1\nline2"
