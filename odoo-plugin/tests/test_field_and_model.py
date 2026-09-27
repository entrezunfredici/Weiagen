"""w_main.data_manager.field / models_service — SDKModel declarative schema."""

import pytest

from w_main.data_manager import BoolField, IntField, ListField, SDKModel, SecretField, StringField


class Widget(SDKModel):
    id: str = StringField(primary_key=True)
    label: str = StringField(default="")
    token: str = SecretField()
    count: int = IntField(default=0)
    active: bool = BoolField(default=True)
    tags: list = ListField()


def test_pk_field_name_detected():
    assert Widget._pk_field_name() == "id"


def test_defaults_applied_when_not_provided():
    w = Widget(id="w1")
    assert w.label == ""
    assert w.count == 0
    assert w.active is True
    assert w.tags == []
    assert w.token is None  # SecretField has no default -> None


def test_explicit_values_override_defaults():
    w = Widget(id="w1", label="Widget One", count=5, active=False, tags=["a", "b"])
    assert w.label == "Widget One"
    assert w.count == 5
    assert w.active is False
    assert w.tags == ["a", "b"]


def test_list_field_default_is_not_shared_between_instances():
    a = Widget(id="a")
    b = Widget(id="b")
    a.tags.append("x")
    assert b.tags == []


def test_get_pk():
    w = Widget(id="w1")
    assert w.get_pk() == "w1"


def test_to_record_excludes_secret_fields():
    w = Widget(id="w1", label="L", token="s3cret")
    record = w.to_record()
    assert "token" not in record
    assert record == {"id": "w1", "label": "L", "count": 0, "active": True, "tags": []}


def test_secret_items_excludes_none_values():
    w = Widget(id="w1", token=None)
    assert w.secret_items() == {}
    w2 = Widget(id="w2", token="s3cret")
    assert w2.secret_items() == {"token": "s3cret"}


def test_from_record_roundtrip():
    w = Widget(id="w1", label="L", token="s3cret", count=3, active=False, tags=["x"])
    record = w.to_record()
    secrets = w.secret_items()
    rebuilt = Widget.from_record(record, **secrets)
    assert rebuilt.id == "w1"
    assert rebuilt.label == "L"
    assert rebuilt.token == "s3cret"
    assert rebuilt.count == 3
    assert rebuilt.active is False
    assert rebuilt.tags == ["x"]


def test_repr_masks_secret_fields():
    w = Widget(id="w1", token="s3cret")
    assert "s3cret" not in repr(w)
    assert "token=***" in repr(w)


def test_model_without_primary_key_raises_on_get_pk():
    class NoPk(SDKModel):
        name: str = StringField()

    instance = NoPk(name="x")
    with pytest.raises(ValueError):
        instance.get_pk()
