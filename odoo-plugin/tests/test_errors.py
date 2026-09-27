"""w_main.errors_manager.errors — ConnectorError and its subclasses."""

from w_main.errors_manager.errors import (
    AuthorizationError,
    ConfigurationError,
    ConfirmationRequiredError,
    ConnectorError,
    NotFoundError,
    ServiceError,
    ValidationError,
)

_SUBCLASS_CODES = {
    ValidationError: "VALIDATION_ERROR",
    AuthorizationError: "AUTHORIZATION_DENIED",
    ConfirmationRequiredError: "CONFIRMATION_REQUIRED",
    NotFoundError: "NOT_FOUND",
    ServiceError: "SERVICE_ERROR",
    ConfigurationError: "CONFIGURATION_ERROR",
}


def test_connector_error_to_dict_shape():
    err = ConnectorError("SOME_CODE", "Something broke", {"key": "value"})
    assert err.to_dict() == {
        "ok": False,
        "error": {"code": "SOME_CODE", "message": "Something broke", "details": {"key": "value"}},
    }


def test_connector_error_to_dict_defaults_details_to_empty_dict():
    err = ConnectorError("SOME_CODE", "Something broke")
    assert err.to_dict()["error"]["details"] == {}


def test_each_subclass_carries_its_documented_code():
    for cls, expected_code in _SUBCLASS_CODES.items():
        err = cls("message", {"a": 1})
        assert err.code == expected_code
        assert err.to_dict()["error"] == {"code": expected_code, "message": "message", "details": {"a": 1}}


def test_subclasses_are_raisable_and_catchable_as_connector_error():
    try:
        raise NotFoundError("nope", {"id": "x"})
    except ConnectorError as exc:
        assert exc.to_dict()["error"]["code"] == "NOT_FOUND"
    else:
        raise AssertionError("expected ConnectorError to be raised")
