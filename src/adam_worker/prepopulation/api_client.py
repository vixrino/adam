"""Client HTTP du worker vers l'API interne.

Le worker pourrait ecrire les DOCUMENT_FIELD directement en base. Passer par
l'API est un choix explicite : la coherence field_spec/schema et la contrainte
d'unicite vivent alors dans adam_api.services.document_fields, une seule fois,
au lieu d'etre reimplementees ici.

Authentification
----------------
La cle de service dediee aux appels worker vers API n'existe pas encore. Le
header est donc construit par _auth_headers, qui rend un dictionnaire vide tant
qu'aucune cle n'est fournie : le jour ou elle arrive, une valeur a passer au
constructeur suffit, sans toucher aux trois methodes d'appel. C'est le point
d'injection demande pour eviter un refactor.

Reprises
--------
Trois tentatives, backoff simple. Seules les erreurs reseau et les 5xx sont
reessayees : un 404 ou un 422 ne changeront pas d'avis, les rejouer ne ferait
que retarder le passage en ERROR.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Sequence

import httpx

from adam_core.utils.logging import get_logger

logger = get_logger(__name__)

_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = 1.0
_RETRYABLE_STATUS = range(500, 600)


class ApiClientError(Exception):
    """Echec d'un appel a l'API interne, apres epuisement des tentatives."""


class ApiClient:
    """Appels au sous-ensemble d'endpoints dont la pre-alimentation a besoin."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: Optional[str] = None,
        timeout_seconds: float = 10.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        # Un client injecte n'est pas ferme par aclose : il appartient a
        # l'appelant, qui l'a probablement partage entre plusieurs consommateurs.
        self._external_client = client is not None
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    def _auth_headers(self) -> Dict[str, str]:
        """Point d'injection de l'authentification service a service.

        Vide tant qu'aucune cle n'est configuree, ce qui correspond au
        comportement DEV actuel.
        """
        if not self.api_key:
            return {}
        return {"X-Internal-Token": self.api_key}

    async def aclose(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    async def __aenter__(self) -> "ApiClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    # -- Transport ----------------------------------------------------------

    async def _request(
        self, method: str, path: str, *, json: Optional[Dict[str, Any]] = None
    ) -> Any:
        url = f"{self.base_url}{path}"
        last_error: Optional[Exception] = None

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = await self._client.request(
                    method, url, json=json, headers=self._auth_headers()
                )
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "appel API en echec reseau [%s %s tentative=%s/%s]",
                    method,
                    path,
                    attempt,
                    _MAX_ATTEMPTS,
                )
            else:
                if response.status_code not in _RETRYABLE_STATUS:
                    if response.status_code >= 400:
                        # 4xx : la demande est en cause, la rejouer est inutile.
                        raise ApiClientError(
                            f"{method} {path} -> {response.status_code} {response.text[:200]}"
                        )
                    return response.json() if response.content else None
                last_error = ApiClientError(f"{method} {path} -> {response.status_code}")
                logger.warning(
                    "appel API en erreur serveur [%s %s status=%s tentative=%s/%s]",
                    method,
                    path,
                    response.status_code,
                    attempt,
                    _MAX_ATTEMPTS,
                )

            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_BACKOFF_SECONDS * attempt)

        raise ApiClientError(f"{method} {path} : {_MAX_ATTEMPTS} tentatives echouees") from (
            last_error
        )

    # -- Endpoints ----------------------------------------------------------

    async def get_dataset(self, dataset_id: int) -> Dict[str, Any]:
        result: Dict[str, Any] = await self._request("GET", f"/datasets/{dataset_id}")
        return result

    async def get_schema(self, schema_id: int) -> Dict[str, Any]:
        """Le schema porte ses field_specs : un seul appel suffit."""
        result: Dict[str, Any] = await self._request("GET", f"/schemas/{schema_id}")
        return result

    async def create_fields_bulk(
        self, document_id: int, fields: Sequence[Dict[str, Any]]
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = await self._request(
            "POST",
            f"/documents/{document_id}/fields/bulk",
            json={"fields": list(fields)},
        )
        return result

    async def get_field_specs(self, dataset_id: int) -> List[Dict[str, Any]]:
        """Raccourci : dataset -> schema -> field_specs, les deux appels chaines."""
        dataset = await self.get_dataset(dataset_id)
        schema_id = dataset.get("schema_id")
        if schema_id is None:
            raise ApiClientError(f"dataset {dataset_id} sans schema_id")
        schema = await self.get_schema(int(schema_id))
        specs: List[Dict[str, Any]] = schema.get("field_specs", [])
        return specs
