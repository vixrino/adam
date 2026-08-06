"""Test manuel de bout en bout du PrepopulationWorker.

Le worker appelle l'API en HTTP. Le script n'a pourtant pas besoin d'un serveur :
httpx sait parler a une application ASGI en memoire, et ApiClient accepte un
client injecte. Les appels traversent donc le vrai routeur, le vrai service et la
vraie base — seul le transport reseau est court-circuite.

Deroule
-------
1. Cree la chaine minimale : Organisation, Project, DocSchema, 4 FieldSpec,
   Dataset, File, puis un Document en statut INGESTED.
2. Fait tourner un cycle unique avec un connecteur OCR pilote.
3. Relit les DOCUMENT_FIELD crees et le statut du document, et compare.
4. Rejoue les scenarios d'echec, chacun sur son propre document.
5. Supprime tout, sauf si --keep.

Scenarios
---------
    OCR complet      les 4 champs detectes, valeurs et confiances posees
    OCR partiel      2 champs sur 4, les autres crees vides
    OCR indisponible aucun champ detecte, document quand meme en IN_PROGRESS
    OCR en echec     document en ERROR
    schema vide      document en ERROR
    idempotence      un second cycle ne cree aucun doublon
    isolation        un document en echec n'empeche pas le suivant d'aboutir

Usage
-----
    python scripts/test_prepopulation_worker.py
    python scripts/test_prepopulation_worker.py --keep

Prerequis : base accessible et migree jusqu'a d4e5f6a7b8c9. Aucun serveur a
lancer, aucun moteur OCR reel.
"""

from __future__ import annotations

# pylint: disable=wrong-import-position,not-callable
# Les imports suivent le sys.path.insert ci-dessous, qui expose src/.

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import httpx  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from adam_api.dependencies.auth import ServiceCaller, get_caller  # noqa: E402
from adam_api.main import app  # noqa: E402
from adam_core.core.config import get_core_settings  # noqa: E402
from adam_core.db.session import get_async_session, init_engine  # noqa: E402
from adam_core.enums.ocr import OcrProvider  # noqa: E402
from adam_core.enums.status import (  # noqa: E402
    DatasetStatus,
    DocumentStatus,
    FieldValueType,
    ProjectStatus,
)
from adam_core.models import (  # noqa: E402
    Dataset,
    DocSchema,
    Document,
    DocumentField,
    FieldSpec,
    File,
    Organisation,
    Project,
)
from adam_core.utils.hashing import sha256_bytes  # noqa: E402
from adam_worker.connectors.mock import MockOcrConnector  # noqa: E402
from adam_worker.prepopulation.api_client import ApiClient  # noqa: E402
from adam_worker.prepopulation.poller import PrepopulationWorker  # noqa: E402

SEPARATOR = "=" * 74
MARKER = "prepop-test"

#: Les quatre champs du schema, en cle pointee comme le contrat OCR les nomme.
FIELD_KEYS = [
    "demandeur.nom",
    "demandeur.prenom",
    "bien.adresse",
    "bien.valeur",
]


@dataclass
class Fixture:
    organisation_id: int
    dataset_id: int
    empty_dataset_id: int
    schema_id: int


# ---------------------------------------------------------------------------
# Transport : l'application ASGI, sans serveur
# ---------------------------------------------------------------------------


def detect_api_prefix() -> str:
    """Prefixe sous lequel l'application monte ses routeurs.

    Les projets ne s'accordent pas : certains servent a la racine, d'autres sous
    /api/v1. Le deviner evite un reglage a maintenir dans deux depots — et une
    erreur silencieuse, puisqu'un mauvais prefixe donne des 404 que le worker
    traduit en documents ERROR sans que rien ne signale la vraie cause.

    On repere la route de creation en lot, dont le chemin est connu, et on en
    retire le suffixe pour obtenir ce qui la precede.
    """
    suffix = "/documents/{document_id}/fields/bulk"
    for path in app.openapi()["paths"]:
        if path.endswith(suffix):
            return path[: -len(suffix)]
    return ""


def build_api_client() -> ApiClient:
    """Client HTTP branche directement sur l'app FastAPI.

    L'authentification est court-circuitee par un ServiceCaller : le worker
    n'a pas encore de cle de service, et une session non scopee est de toute
    facon ce qu'un appel machine doit obtenir.
    """
    app.dependency_overrides[get_caller] = lambda: ServiceCaller(service_name=MARKER)
    prefix = detect_api_prefix()
    base_url = f"http://memoire{prefix}"
    print(f"  API en memoire, prefixe detecte : {prefix or '(racine)'}")
    transport = httpx.ASGITransport(app=app)
    return ApiClient(
        base_url=base_url,
        client=httpx.AsyncClient(transport=transport, base_url="http://memoire"),
    )


# ---------------------------------------------------------------------------
# Mise en place
# ---------------------------------------------------------------------------


async def build_fixture() -> Fixture:
    """Cree le socle commun : un schema a 4 champs, et un dataset sans schema utile."""
    async with get_async_session() as db:
        organisation = Organisation(name=f"Org {MARKER}", slug=f"org-{MARKER}")
        db.add(organisation)
        await db.flush()

        project = Project(
            organisation_id=organisation.id,
            name=f"Projet {MARKER}",
            status=ProjectStatus.ACTIVE.value,
        )
        db.add(project)
        await db.flush()

        schema = DocSchema(
            project_id=project.id,
            version=1,
            name=f"Schema {MARKER}",
            document_type="PREPOP_TEST",
        )
        empty_schema = DocSchema(
            project_id=project.id,
            version=1,
            name=f"Schema vide {MARKER}",
            document_type="PREPOP_TEST_VIDE",
        )
        db.add_all([schema, empty_schema])
        await db.flush()

        db.add_all(
            [
                FieldSpec(
                    schema_id=schema.id,
                    page=1,
                    section_id=key.split(".", 1)[0],
                    section_label=key.split(".", 1)[0].capitalize(),
                    field_key=key,
                    display_label=key,
                    value_type=FieldValueType.TEXT.value,
                    required=False,
                    display_order=index,
                    polygon=[float(index), 1.0, 2.0, 3.0],
                )
                for index, key in enumerate(FIELD_KEYS)
            ]
        )

        dataset = Dataset(
            project_id=project.id,
            schema_id=schema.id,
            name=f"Dataset {MARKER}",
            ocr_provider=OcrProvider.PULSAR.value,
            status=DatasetStatus.ACTIVE.value,
            configs={},
        )
        empty_dataset = Dataset(
            project_id=project.id,
            schema_id=empty_schema.id,
            name=f"Dataset sans champ {MARKER}",
            ocr_provider=OcrProvider.PULSAR.value,
            status=DatasetStatus.ACTIVE.value,
            configs={},
        )
        db.add_all([dataset, empty_dataset])
        await db.flush()

        return Fixture(
            organisation_id=organisation.id,
            dataset_id=dataset.id,
            empty_dataset_id=empty_dataset.id,
            schema_id=schema.id,
        )


async def new_document(dataset_id: int, label: str) -> int:
    """Un document INGESTED, pret a etre pre-alimente."""
    async with get_async_session() as db:
        payload = f"{MARKER}-{label}".encode()
        file_row = File(
            file_path=f"/pvc/{MARKER}/{label}.pdf",
            storage_type="PVC",
            mime_type="application/pdf",
            page_count=2,
            file_size_bytes=len(payload),
            sha256_checksum=sha256_bytes(payload),
        )
        db.add(file_row)
        await db.flush()

        document = Document(
            dataset_id=dataset_id,
            file_id=file_row.id,
            file_name=f"{label}.pdf",
            status=DocumentStatus.INGESTED.value,
        )
        db.add(document)
        await db.flush()
        return int(document.id)


# ---------------------------------------------------------------------------
# Lecture du resultat
# ---------------------------------------------------------------------------


async def read_result(document_id: int) -> Tuple[str, List[DocumentField]]:
    async with get_async_session() as db:
        status = (
            await db.execute(select(Document.status).where(Document.id == document_id))
        ).scalar_one()
        fields = list(
            (
                await db.execute(
                    select(DocumentField)
                    .where(DocumentField.document_id == document_id)
                    .order_by(DocumentField.field_spec_id)
                )
            )
            .scalars()
            .all()
        )
        return str(status), fields


def check(label: str, condition: bool, detail: str = "") -> int:
    """Affiche le verdict d'une verification et rend 1 si elle echoue."""
    marker = "OK " if condition else "ECHEC"
    suffix = f"  {detail}" if detail else ""
    print(f"  [{marker}] {label}{suffix}")
    return 0 if condition else 1


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


async def run_case(
    fixture: Fixture,
    api: ApiClient,
    label: str,
    connector: MockOcrConnector,
    dataset_id: Optional[int] = None,
) -> Tuple[str, List[DocumentField]]:
    """Cree un document, fait tourner un cycle, rend son etat final."""
    document_id = await new_document(dataset_id or fixture.dataset_id, label)
    worker = PrepopulationWorker(connector=connector, api_client=api, pvc_root=Path("/inexistant"))
    await worker.poll()
    return await read_result(document_id)


async def _case_ocr_complet(fixture: Fixture, api: ApiClient) -> int:
    failures = 0

    print(SEPARATOR)
    print(" OCR complet")
    print(SEPARATOR)
    status, fields = await run_case(
        fixture, api, "complet", MockOcrConnector(FIELD_KEYS, value="Dupont")
    )
    failures += check("document en IN_PROGRESS", status == DocumentStatus.IN_PROGRESS.value, status)
    failures += check("4 champs crees", len(fields) == 4, f"{len(fields)} champ(s)")
    failures += check(
        "toutes les valeurs viennent de l'OCR",
        bool(fields) and all(f.ocr_value == "Dupont" for f in fields),
    )
    failures += check(
        "resolved_value initialisee a la valeur OCR",
        bool(fields) and all(f.resolved_value == "Dupont" for f in fields),
    )
    failures += check(
        "resolved_by = ocr_system",
        bool(fields) and all(f.resolved_by == "ocr_system" for f in fields),
    )
    failures += check(
        "polygone et confiance de l'OCR",
        bool(fields) and all(f.ocr_confidence == 0.95 and f.ocr_polygon for f in fields),
    )

    return failures


async def _case_ocr_partiel(fixture: Fixture, api: ApiClient) -> int:
    failures = 0

    print()
    print(SEPARATOR)
    print(" OCR partiel : 2 champs sur 4")
    print(SEPARATOR)
    status, fields = await run_case(
        fixture, api, "partiel", MockOcrConnector(FIELD_KEYS[:2], value="Martin")
    )
    detected = [f for f in fields if f.ocr_value is not None]
    empty = [f for f in fields if f.ocr_value is None]
    failures += check("document en IN_PROGRESS", status == DocumentStatus.IN_PROGRESS.value)
    failures += check(
        "le schema commande : 4 champs malgre 2 detections", len(fields) == 4, f"{len(fields)}"
    )
    failures += check("2 champs renseignes", len(detected) == 2)
    failures += check(
        "les 2 autres sont vides, sans resolveur",
        len(empty) == 2 and all(f.resolved_by is None and f.resolved_value is None for f in empty),
    )
    failures += check(
        "polygone du schema en repli sur les champs vides",
        len(empty) == 2 and all(f.ocr_polygon is not None for f in empty),
    )

    return failures


async def _case_ocr_indisponible(fixture: Fixture, api: ApiClient) -> int:
    failures = 0

    print()
    print(SEPARATOR)
    print(" OCR indisponible")
    print(SEPARATOR)
    status, fields = await run_case(
        fixture, api, "indisponible", MockOcrConnector(available=False)
    )
    failures += check(
        "document en IN_PROGRESS malgre tout",
        status == DocumentStatus.IN_PROGRESS.value,
        status,
    )
    failures += check("les 4 champs existent, vides", len(fields) == 4)
    failures += check(
        "aucun resolveur pose",
        len(fields) == 4 and all(f.resolved_by is None for f in fields),
    )

    return failures


async def _case_echecs(fixture: Fixture, api: ApiClient) -> int:
    failures = 0

    print()
    print(SEPARATOR)
    print(" Echecs bloquants")
    print(SEPARATOR)
    status, fields = await run_case(fixture, api, "echec-ocr", MockOcrConnector(failing=True))
    failures += check("connecteur en echec -> ERROR", status == DocumentStatus.ERROR.value, status)
    failures += check("aucun champ cree", len(fields) == 0)

    status, fields = await run_case(
        fixture,
        api,
        "schema-vide",
        MockOcrConnector(FIELD_KEYS),
        dataset_id=fixture.empty_dataset_id,
    )
    failures += check("schema sans field_spec -> ERROR", status == DocumentStatus.ERROR.value)

    return failures


async def _case_idempotence(fixture: Fixture, api: ApiClient) -> int:
    failures = 0

    print()
    print(SEPARATOR)
    print(" Idempotence")
    print(SEPARATOR)
    document_id = await new_document(fixture.dataset_id, "idempotence")
    worker = PrepopulationWorker(
        connector=MockOcrConnector(FIELD_KEYS), api_client=api, pvc_root=Path("/inexistant")
    )
    await worker.poll()
    _status, first = await read_result(document_id)

    # On remet le document dans la file : le worker le reprend, et le lot doit
    # ignorer les champs deja crees au lieu d'echouer sur la contrainte unique.
    await set_status(document_id, DocumentStatus.INGESTED)
    await worker.poll()
    status, second = await read_result(document_id)

    failures += check("aucun doublon au second passage", len(second) == len(first) == 4)
    failures += check(
        "document de nouveau en IN_PROGRESS",
        status == DocumentStatus.IN_PROGRESS.value,
    )

    return failures


async def _case_isolation(fixture: Fixture, api: ApiClient) -> int:
    failures = 0

    print()
    print(SEPARATOR)
    print(" Isolation des erreurs")
    print(SEPARATOR)
    bad_id = await new_document(fixture.empty_dataset_id, "isolation-ko")
    good_id = await new_document(fixture.dataset_id, "isolation-ok")
    worker = PrepopulationWorker(
        connector=MockOcrConnector(FIELD_KEYS), api_client=api, pvc_root=Path("/inexistant")
    )
    await worker.poll()
    bad_status, _ = await read_result(bad_id)
    good_status, good_fields = await read_result(good_id)
    failures += check(
        "le document en echec passe en ERROR", bad_status == DocumentStatus.ERROR.value
    )
    failures += check(
        "le suivant est traite quand meme",
        good_status == DocumentStatus.IN_PROGRESS.value and len(good_fields) == 4,
    )

    return failures


async def run_scenarios(fixture: Fixture, api: ApiClient) -> int:
    """Enchaine les scenarios, chacun sur ses propres documents."""
    cases = (
        _case_ocr_complet,
        _case_ocr_partiel,
        _case_ocr_indisponible,
        _case_echecs,
        _case_idempotence,
        _case_isolation,
    )
    failures = 0
    for case in cases:
        failures += await case(fixture, api)
    return failures


async def set_status(document_id: int, status: DocumentStatus) -> None:
    async with get_async_session() as db:
        document = await db.get(Document, document_id)
        if document is not None:
            document.status = status.value


# ---------------------------------------------------------------------------
# Nettoyage
# ---------------------------------------------------------------------------


async def cleanup() -> None:
    async with get_async_session() as db:
        organisation_id = (
            await db.execute(select(Organisation.id).where(Organisation.slug == f"org-{MARKER}"))
        ).scalar_one_or_none()
        if organisation_id is None:
            return

        project_ids = _ids(
            await db.execute(select(Project.id).where(Project.organisation_id == organisation_id))
        )
        dataset_ids = _ids(
            await db.execute(select(Dataset.id).where(Dataset.project_id.in_(project_ids)))
        )
        document_ids = _ids(
            await db.execute(select(Document.id).where(Document.dataset_id.in_(dataset_ids)))
        )
        file_ids = _ids(
            await db.execute(select(Document.file_id).where(Document.id.in_(document_ids)))
        )
        schema_ids = _ids(
            await db.execute(select(DocSchema.id).where(DocSchema.project_id.in_(project_ids)))
        )

        await db.execute(delete(DocumentField).where(DocumentField.document_id.in_(document_ids)))
        await db.execute(delete(Document).where(Document.id.in_(document_ids)))
        await db.execute(delete(File).where(File.id.in_(file_ids)))
        await db.execute(delete(Dataset).where(Dataset.id.in_(dataset_ids)))
        await db.execute(delete(FieldSpec).where(FieldSpec.schema_id.in_(schema_ids)))
        await db.execute(delete(DocSchema).where(DocSchema.id.in_(schema_ids)))
        await db.execute(delete(Project).where(Project.id.in_(project_ids)))
        await db.execute(delete(Organisation).where(Organisation.id == organisation_id))
    print("  Jeu de test supprime")


def _ids(result: object) -> List[int]:
    return [int(value) for value in result.scalars().all()]  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------


async def main(keep: bool) -> int:
    init_engine(get_core_settings().async_database_url)
    await cleanup()

    fixture = await build_fixture()
    api = build_api_client()
    print(f"  Schema {fixture.schema_id} cree avec {len(FIELD_KEYS)} champs\n")

    try:
        failures = await run_scenarios(fixture, api)
    finally:
        await api.aclose()
        print()
        if keep:
            print("  --keep : le jeu de test est conserve")
        else:
            await cleanup()

    print()
    if failures:
        print(f" {failures} verification(s) en echec.")
    else:
        print(" PrepopulationWorker conforme.")
    return 1 if failures else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test de bout en bout du PrepopulationWorker")
    parser.add_argument("--keep", action="store_true", help="ne pas supprimer le jeu de test")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(keep=_parse_args().keep)))
