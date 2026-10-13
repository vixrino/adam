"""T7 : les lignes d'un tableau repetable (prets n° 1 a 6) sont lues et rangees
chacune dans sa ligne, au lieu de recevoir toutes la valeur de la premiere.

    CA-1  n lignes lues donnent n DOCUMENT_FIELD distincts, chacun sa valeur
    CA-2  un second passage ne cree aucun doublon
    CA-3  la contrainte d'unicite (document_id, field_spec_id, group_id) contre
          une vraie base : NON verifiee ici, faute de PostgreSQL. Elle est
          declaree sur le modele (uq_document_field_doc_spec_group) et
          appliquee en applicatif par create_bulk, que CA-2 couvre.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest

from adam_api.services import document_fields as service
from adam_core.schemas.interface_contract import (
    KVPair,
    KVTextValue,
    Page,
    Section,
    SmartdocDocument,
)
from adam_worker.connectors.mistral import _CONSIGNE, MistralOcrConnector
from adam_worker.connectors.modele import ModeleDocument
from adam_worker.prepopulation.merger import merge

ENDPOINT = "https://mistral.test"


def _specs_prets(nombre: int = 6) -> List[Dict[str, Any]]:
    """Une FIELD_SPEC par ligne, comme le seed : field_key partiel, group_id."""
    return [
        {
            "id": 100 + n,
            "page": 10,
            "section_id": "credits_consommation",
            "field_key": "reference",
            "display_label": f"Reference du pret - Pret n° {n}",
            "description": "Reference du pret",
            "value_type": "TEXT",
            "group_id": f"pret_{n}",
            "polygon": None,
        }
        for n in range(1, nombre + 1)
    ]


def _ocr(*paires: KVPair) -> SmartdocDocument:
    return SmartdocDocument(
        smartdoc_version="0.3",
        document_id="t7",
        page_count=1,
        pages=[
            Page(
                page_number=10,
                width=1.0,
                height=1.0,
                sections=[
                    Section(id="credits_consommation", label="Credits", kv_pairs=list(paires))
                ],
            )
        ],
        metadata={"provider": "test"},
    )


def _kv(valeur: str, group_id: Any = None) -> KVPair:
    return KVPair(
        id="credits_consommation.reference",
        group_id=group_id,
        value=KVTextValue(text=valeur),
    )


# -- Merger (CA-1) -----------------------------------------------------------------


class TestMerger:
    def test_chaque_ligne_recoit_sa_propre_valeur(self) -> None:
        """Prets 1, 2, 3 et 5 remplis, 4 vide : comme sur le CERFA reel."""
        ocr = _ocr(
            _kv("ADVANZIA", "pret_1"),
            _kv("DIAC", "pret_2"),
            _kv("CARREFOUR", "pret_3"),
            _kv("CIC", "pret_5"),
        )
        payloads = merge(_specs_prets(), ocr)
        valeurs = {p["group_id"]: p["ocr_value"] for p in payloads}
        assert valeurs == {
            "pret_1": "ADVANZIA",
            "pret_2": "DIAC",
            "pret_3": "CARREFOUR",
            "pret_4": None,
            "pret_5": "CIC",
            "pret_6": None,
        }
        assert len({(p["field_spec_id"], p["group_id"]) for p in payloads}) == 6

    def test_valeur_sans_instance_ne_remplit_que_la_premiere_ligne(self) -> None:
        """Un connecteur qui ignore les repetables (le mock) : avant T7, sa
        valeur etait recopiee dans les six lignes."""
        payloads = merge(_specs_prets(), _ocr(_kv("ADVANZIA")))
        remplis = [p["group_id"] for p in payloads if p["ocr_value"] is not None]
        assert remplis == ["pret_1"]

    def test_champ_simple_inchange(self) -> None:
        spec = {
            "id": 1,
            "page": 1,
            "section_id": "deposant",
            "field_key": "deposant.nom",
            "group_id": None,
            "polygon": None,
        }
        kv = KVPair(id="deposant.nom", value=KVTextValue(text="DUPONT"))
        ocr = SmartdocDocument(
            smartdoc_version="0.3",
            document_id="t7",
            page_count=1,
            pages=[
                Page(
                    page_number=1,
                    width=1.0,
                    height=1.0,
                    sections=[Section(id="deposant", label="Deposant", kv_pairs=[kv])],
                )
            ],
            metadata={"provider": "test"},
        )
        assert merge([spec], ocr)[0]["ocr_value"] == "DUPONT"


# -- Connecteur ---------------------------------------------------------------------


def _routeur(annotation: Dict[str, Any], journal: List[httpx.Request]) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        journal.append(request)
        if request.url.path.endswith("/v1/ocr"):
            return httpx.Response(200, json={"pages": [{"markdown": "| Pret | ... |"}]})
        corps = json.loads(request.content)
        if corps["response_format"]["json_schema"]["name"] == "identification_page":
            contenu = {"page": 10}
        else:
            contenu = annotation
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(contenu)}}]}
        )

    return handler


def _connecteur(handler: Any) -> MistralOcrConnector:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return MistralOcrConnector(api_key="cle", endpoint=ENDPOINT, client=client)


def _modele() -> ModeleDocument:
    return ModeleDocument.depuis_schema(
        {
            "name": "CERFA",
            "pages": [{"page_number": 10, "description": "Credits a la consommation"}],
            "field_specs": _specs_prets(3),
        }
    )


class TestConnecteur:
    def test_une_propriete_par_ligne_et_redecoupage(self, tmp_path: Path) -> None:
        image = tmp_path / "0001.png"
        image.write_bytes(b"x")
        journal: List[httpx.Request] = []
        annotation = {
            "credits_consommation.pret_1.reference": "ADVANZIA",
            "credits_consommation.pret_2.reference": None,
            "credits_consommation.pret_3.reference": "CARREFOUR",
        }
        doc = asyncio.run(_connecteur(_routeur(annotation, journal)).extract([image], _modele()))
        assert doc is not None

        envoye = json.loads(journal[-1].content)["response_format"]["json_schema"]["schema"]
        assert set(envoye["properties"]) == {
            f"credits_consommation.pret_{n}.reference" for n in (1, 2, 3)
        }
        paires = [kv for _, _, kv in doc.iter_kv_pairs()]
        assert {(kv.id, kv.group_id, kv.extracted_value) for kv in paires} == {
            ("credits_consommation.reference", "pret_1", "ADVANZIA"),
            ("credits_consommation.reference", "pret_2", None),
            ("credits_consommation.reference", "pret_3", "CARREFOUR"),
        }

    def test_reponse_imbriquee_par_instance(self, tmp_path: Path) -> None:
        """Le modele regroupe parfois par section puis par ligne."""
        image = tmp_path / "0001.png"
        image.write_bytes(b"x")
        annotation = {"credits_consommation": {"pret_2": {"reference": "DIAC"}}}
        doc = asyncio.run(_connecteur(_routeur(annotation, [])).extract([image], _modele()))
        assert doc is not None
        lues = {kv.group_id: kv.extracted_value for _, _, kv in doc.iter_kv_pairs()}
        assert lues["pret_2"] == "DIAC"

    def test_la_consigne_range_par_numero_imprime(self) -> None:
        assert "designe la ligne imprimee n° 5" in _CONSIGNE
        assert "la ligne 4 reste null et la 5 recoit ses valeurs" in _CONSIGNE
        # La regle d'avant T7 contredisait la lecture des tableaux.
        assert "ne rends que la premiere" not in _CONSIGNE


# -- create_bulk (CA-2) ----------------------------------------------------------------


class TestIdempotence:
    def test_second_passage_sans_doublon(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payloads = merge(_specs_prets(3), _ocr(_kv("A", "pret_1"), _kv("B", "pret_2")))
        ids = {p["field_spec_id"] for p in payloads}
        deja: set = set()

        async def schema_id(db: Any, document: Any) -> int:
            return 1

        async def valides(db: Any, schema: int) -> set:
            return ids

        async def existants(db: Any, document_id: int) -> set:
            return set(deja)

        monkeypatch.setattr(service, "resolve_schema_id", schema_id)
        monkeypatch.setattr(service, "_valid_field_spec_ids", valides)
        monkeypatch.setattr(service, "_existing_keys", existants)

        class _Db:
            def add(self, row: Any) -> None:
                deja.add((row.field_spec_id, row.group_id))

            async def flush(self) -> None:
                return None

        document = type("D", (), {"id": 5})()
        premier = asyncio.run(service.create_bulk(_Db(), document, payloads))
        second = asyncio.run(service.create_bulk(_Db(), document, payloads))
        assert len(premier.created) == 3 and premier.skipped == []
        assert second.created == [] and len(second.skipped) == 3
        # Trois lignes distinctes, distinguees par group_id.
        assert {k[1] for k in second.skipped} == {"pret_1", "pret_2", "pret_3"}
