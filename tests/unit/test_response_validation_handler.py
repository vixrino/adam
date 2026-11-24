"""Une reponse qui ne passe pas son response_model : 500 lisible, sans donnees dans le log."""

import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from adam_api import main
from adam_core.utils.exceptions import response_validation_handler


class _Out(BaseModel):
    updated_at: int


def test_handler_logs_field_and_type_but_not_the_value(caplog) -> None:
    app = FastAPI()
    app.add_exception_handler(main.ResponseValidationError, response_validation_handler)

    @app.get("/x", response_model=_Out)
    async def _route() -> dict:
        return {"updated_at": "valeur-secrete"}

    with caplog.at_level(logging.ERROR):
        response = TestClient(app, raise_server_exceptions=False).get("/x")

    assert response.status_code == 500
    assert json.loads(response.text) == {"detail": "Erreur interne du serveur"}
    assert "updated_at" in caplog.text and "int_parsing" in caplog.text
    assert "valeur-secrete" not in caplog.text


def test_main_registers_the_handler() -> None:
    assert main.app.exception_handlers[main.ResponseValidationError] is response_validation_handler
