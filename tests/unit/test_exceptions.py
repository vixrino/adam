"""
Tests unitaires — adam_core/utils/exceptions.py
"""

import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakeModel:
    __tablename__ = "organisation"


class Project:
    pass


FakeModelNoTablename = Project


# ---------------------------------------------------------------------------
# _name
# ---------------------------------------------------------------------------


class TestName:
    def test_uses_tablename_when_present(self) -> None:
        assert _name(FakeModel) == "Organisation"

    def test_falls_back_to_class_name(self) -> None:
        assert _name(FakeModelNoTablename) == "Project"

    def test_capitalizes_result(self) -> None:
        class Lower:
            __tablename__ = "user_project"

        assert _name(Lower) == "User_project"


# ---------------------------------------------------------------------------
# raise_not_found
# ---------------------------------------------------------------------------


class TestRaiseNotFound:
    def test_raises_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found(FakeModel)
        assert exc_info.value.status_code == 404

    def test_default_detail_uses_tablename(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found(FakeModel)
        assert exc_info.value.detail == NOT_FOUND.format("Organisation")

    def test_custom_detail_overrides_default(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found(FakeModel, detail="identifiant inconnu")
        assert exc_info.value.detail == "identifiant inconnu"

    def test_return_type_is_no_return(self) -> None:
        """raise_not_found ne retourne jamais — toujours une exception."""
        with pytest.raises(HTTPException):
            raise_not_found(FakeModel)


# ---------------------------------------------------------------------------
# raise_already_archived
# ---------------------------------------------------------------------------


class TestRaiseAlreadyArchived:
    def test_raises_409(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            raise_already_archived(FakeModel)
        assert exc_info.value.status_code == 409

    def test_detail_format(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            raise_already_archived(FakeModel)
        assert exc_info.value.detail == ALREADY_ARCHIVED.format("Organisation")


# ---------------------------------------------------------------------------
# raise_not_archived
# ---------------------------------------------------------------------------


class TestRaiseNotArchived:
    def test_raises_409(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            raise_not_archived(FakeModel)
        assert exc_info.value.status_code == 409

    def test_detail_format(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            raise_not_archived(FakeModel)
        assert exc_info.value.detail == NOT_ARCHIVED.format("Organisation")


# ---------------------------------------------------------------------------
# raise_already_exists
# ---------------------------------------------------------------------------


class TestRaiseAlreadyExists:
    def test_raises_409(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            raise_already_exists(FakeModel)
        assert exc_info.value.status_code == 409

    def test_detail_format(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            raise_already_exists(FakeModel)
        assert exc_info.value.detail == ALREADY_EXISTS.format("Organisation")


# ---------------------------------------------------------------------------
# raise_conflict
# ---------------------------------------------------------------------------


class TestRaiseConflict:
    def test_raises_409(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            raise_conflict(FakeModel, "deja soumis")
        assert exc_info.value.status_code == 409

    def test_detail_includes_model_and_message(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            raise_conflict(FakeModel, "deja soumis")
        assert "Organisation" in exc_info.value.detail
        assert "deja soumis" in exc_info.value.detail


# ---------------------------------------------------------------------------
# raise_unprocessable
# ---------------------------------------------------------------------------


class TestRaiseUnprocessable:
    def test_raises_422(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            raise_unprocessable("champ invalide")
        assert exc_info.value.status_code == 422

    def test_detail_passthrough(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            raise_unprocessable("champ invalide")
        assert exc_info.value.detail == "champ invalide"


# ---------------------------------------------------------------------------
# http_exception_handler
# ---------------------------------------------------------------------------


class TestHttpExceptionHandler:
    def _make_request(self, path: str = "/test", method: str = "GET") -> MagicMock:
        request = MagicMock()
        request.method = method
        request.url.path = path
        return request

    @pytest.mark.asyncio
    async def test_returns_json_response_with_correct_status(self) -> None:
        request = self._make_request()
        exc = HTTPException(status_code=404, detail="introuvable")
        response = await http_exception_handler(request, exc)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_response_body_contains_detail(self) -> None:
        import json

        request = self._make_request()
        exc = HTTPException(status_code=404, detail="introuvable")
        response = await http_exception_handler(request, exc)
        body = json.loads(response.body)
        assert body["detail"] == "introuvable"

    @pytest.mark.asyncio
    async def test_4xx_does_not_raise(self) -> None:
        request = self._make_request()
        exc = HTTPException(status_code=400, detail="bad request")
        response = await http_exception_handler(request, exc)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_5xx_does_not_raise(self) -> None:
        request = self._make_request()
        exc = HTTPException(status_code=500, detail="erreur interne")
        response = await http_exception_handler(request, exc)
        assert response.status_code == 500
