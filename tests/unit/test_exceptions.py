"""Tests unitaires - adam_core/utils/exceptions.py"""
import pytest
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient

from adam_core.utils.exceptions import (
    _name,
    raise_not_found,
    raise_already_archived,
    raise_not_archived,
    raise_already_exists,
    raise_conflict,
    raise_unprocessable,
    http_exception_handler,
    NOT_FOUND,
    ALREADY_ARCHIVED,
    NOT_ARCHIVED,
    ALREADY_EXISTS,
)


class FakeModel:
    __tablename__ = "organisation"


class FakeModelNoTablename:
    __name__ = "Project"


class TestName:
    def test_uses_tablename_when_present(self) -> None:
        assert _name(FakeModel) == "Organisation"

    def test_falls_back_to_class_name(self) -> None:
        assert _name(FakeModelNoTablename) == "Project"

    def test_capitalizes_result(self) -> None:
        class Lower:
            __tablename__ = "user_project"

        assert _name(Lower) == "User_project"


class TestRaiseNotFound:
    def test_raises_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found(FakeModel)
        assert exc_info.value.status_code == 404
        assert NOT_FOUND.format("Organisation") in str(exc_info.value.detail)


class TestRaiseAlreadyArchived:
    def test_raises_409(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            raise_already_archived(FakeModel)
        assert exc_info.value.status_code == 409
        assert ALREADY_ARCHIVED.format("Organisation") in str(exc_info.value.detail)


class TestHttpExceptionHandler:
    def test_handler_returns_json(self) -> None:
        app = FastAPI()
        app.add_exception_handler(HTTPException, http_exception_handler)
        client = TestClient(app)

        @app.get("/boom")
        def boom() -> None:
            raise HTTPException(status_code=418, detail="teapot")

        response = client.get("/boom")
        assert response.status_code == 418
        assert response.json()["detail"] == "teapot"
