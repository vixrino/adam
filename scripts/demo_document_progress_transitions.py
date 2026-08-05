"""Demonstration des transitions d'etape du DocumentProgressWorker.

Le script test_document_progress_worker.py verifie un instantane : six documents
fabriques a six stades, une passe, six verdicts. Celui-ci verifie autre chose,
et c'est la vraie question posee a un worker d'observation : reagit-il quand les
donnees changent ?

Un seul document est cree, puis pousse d'etape en etape. A chaque etape le
script modifie les tables sources, relance un cycle, relit document_progress et
compare. Il descend ensuite la chaine en sens inverse, parce qu'un constat n'est
pas un statut : retirer l'OCR doit faire reculer l'etape, pas la figer.

Scenarios
---------
    1. INGESTED           document neuf, fichier sans pages rendues
    2. PAGES_RENDERED     file.page_count passe a 2
    3. OCR_AVAILABLE      un OcrResult apparait
    4. FIELDS_PREFILLED   des document_field portent une valeur OCR
    5. ANNOTATION         un job soumis sur les 2 attendus
    6. CONSENSUS_REACHED  le second job est soumis
    7. retour arriere     les pages disparaissent, tout redescend
    8. garde              required_operators a 0 n'annonce pas un consensus

Le worker tourne avec staleness_seconds=0 : chaque appel recalcule, sans quoi il
faudrait attendre 300 secondes entre deux etapes.

Usage
-----
    python scripts/demo_document_progress_transitions.py
    python scripts/demo_document_progress_transitions.py --keep

Le jeu de test est isole dans sa propre organisation et supprime a la fin : le
seed n'est pas touche. Prerequis : base accessible et migree.
"""

from __future__ import annotations

# pylint: disable=wrong-import-position,not-callable
# Les imports suivent le sys.path.insert ci-dessous, qui expose src/.

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import delete, select, update  # noqa: E402

from adam_core.core.config import get_core_settings  # noqa: E402
from adam_core.db.session import get_async_session, init_engine  # noqa: E402
from adam_core.enums.ocr import OcrProvider, StorageMode  # noqa: E402
from adam_core.enums.status import (  # noqa: E402
    DatasetStatus,
    DocumentFieldStatus,
    DocumentStage,
    DocumentStatus,
    FieldValueType,
    JobState,
    JobStep,
    ProjectStatus,
    UserStatus,
)
from adam_core.models import (  # noqa: E402
    Dataset,
    DocSchema,
    Document,
    DocumentField,
    DocumentProgress,
    FieldSpec,
    File,
    Job,
    OcrResult,
    Organisation,
    Project,
    User,
)
from adam_core.utils.hashing import sha256_bytes  # noqa: E402
from adam_worker.document_progress_worker import DocumentProgressWorker  # noqa: E402

SEPARATOR = "=" * 72
MARKER = "transitions-demo"
REQUIRED_OPERATORS = 2
FIELD_COUNT = 4


@dataclass
class Fixture:
    """Les identifiants dont les scenarios ont besoin."""

    organisation_id: int
    user_id: int
    dataset_id: int
    document_id: int
    file_id: int
    field_spec_ids: List[int]


# ---------------------------------------------------------------------------
# Mise en place
# ---------------------------------------------------------------------------


async def build_fixture() -> Fixture:
    """Cree un document neuf : fichier present, pages non rendues, rien d'autre."""
    async with get_async_session() as db:
        organisation = Organisation(name=f"Org {MARKER}", slug=f"org-{MARKER}")
        db.add(organisation)
        await db.flush()

        user = User(
            organisation_id=organisation.id,
            email=f"{MARKER}@example.com",
            full_name="Operateur de demonstration",
            matricule=f"MAT-{MARKER}",
            status=UserStatus.ACTIVE.value,
        )
        project = Project(
            organisation_id=organisation.id,
            name=f"Projet {MARKER}",
            status=ProjectStatus.ACTIVE.value,
        )
        db.add_all([user, project])
        await db.flush()

        schema = DocSchema(
            project_id=project.id,
            version=1,
            name=f"Schema {MARKER}",
            document_type="TRANSITIONS_DEMO",
        )
        db.add(schema)
        await db.flush()

        field_specs = [
            FieldSpec(
                schema_id=schema.id,
                page=1,
                section_id="s1",
                section_label="Section",
                field_key=f"champ_{i}",
                display_label=f"Champ {i}",
                value_type=FieldValueType.TEXT.value,
                required=False,
                display_order=i,
            )
            for i in range(FIELD_COUNT)
        ]
        db.add_all(field_specs)

        dataset = Dataset(
            project_id=project.id,
            schema_id=schema.id,
            name=f"Dataset {MARKER}",
            ocr_provider=OcrProvider.PULSAR.value,
            status=DatasetStatus.ACTIVE.value,
            required_operators=REQUIRED_OPERATORS,
            configs={},
        )
        db.add(dataset)
        await db.flush()

        payload = MARKER.encode()
        file_row = File(
            file_path=f"/pvc/{MARKER}/document.pdf",
            storage_type="PVC",
            mime_type="application/pdf",
            page_count=0,  # pages non rendues : point de depart de la chaine
            file_size_bytes=len(payload),
            sha256_checksum=sha256_bytes(payload),
        )
        db.add(file_row)
        await db.flush()

        document = Document(
            dataset_id=dataset.id,
            file_id=file_row.id,
            file_name="document.pdf",
            status=DocumentStatus.RECEIVED.value,
        )
        db.add(document)
        await db.flush()

        return Fixture(
            organisation_id=organisation.id,
            user_id=user.id,
            dataset_id=dataset.id,
            document_id=document.id,
            file_id=file_row.id,
            field_spec_ids=[spec.id for spec in field_specs],
        )


# ---------------------------------------------------------------------------
# Mutations, une par transition
# ---------------------------------------------------------------------------


async def render_pages(fixture: Fixture) -> None:
    async with get_async_session() as db:
        await db.execute(update(File).where(File.id == fixture.file_id).values(page_count=2))


async def unrender_pages(fixture: Fixture) -> None:
    async with get_async_session() as db:
        await db.execute(update(File).where(File.id == fixture.file_id).values(page_count=0))


async def add_ocr_result(fixture: Fixture) -> None:
    async with get_async_session() as db:
        db.add(
            OcrResult(
                document_id=fixture.document_id,
                dataset_id=fixture.dataset_id,
                storage_mode=StorageMode.JSONB.value,
                raw_json={"marker": MARKER},
            )
        )


async def prefill_fields(fixture: Fixture) -> None:
    """Cree les champs, dont deux portent une valeur OCR."""
    async with get_async_session() as db:
        db.add_all(
            [
                DocumentField(
                    document_id=fixture.document_id,
                    field_spec_id=spec_id,
                    ocr_value="valeur" if position < 2 else None,
                    status=DocumentFieldStatus.PENDING.value,
                )
                for position, spec_id in enumerate(fixture.field_spec_ids)
            ]
        )


async def empty_fields(fixture: Fixture) -> None:
    """Retire les valeurs sans supprimer les lignes : fields_total reste > 0."""
    async with get_async_session() as db:
        await db.execute(
            update(DocumentField)
            .where(DocumentField.document_id == fixture.document_id)
            .values(ocr_value=None, resolved_value=None)
        )


async def submit_job(fixture: Fixture) -> None:
    async with get_async_session() as db:
        db.add(
            Job(
                dataset_id=fixture.dataset_id,
                document_id=fixture.document_id,
                agent_id=fixture.user_id,
                state=JobState.SUBMITTED.value,
                step=JobStep.VALIDATION.value,
            )
        )


async def drop_jobs(fixture: Fixture) -> None:
    async with get_async_session() as db:
        await db.execute(delete(Job).where(Job.document_id == fixture.document_id))


async def drop_ocr(fixture: Fixture) -> None:
    async with get_async_session() as db:
        await db.execute(delete(OcrResult).where(OcrResult.document_id == fixture.document_id))


async def set_required_operators(fixture: Fixture, value: int) -> None:
    async with get_async_session() as db:
        await db.execute(
            update(Dataset).where(Dataset.id == fixture.dataset_id).values(required_operators=value)
        )


# ---------------------------------------------------------------------------
# Boucle de verification
# ---------------------------------------------------------------------------


async def current_stage(document_id: int) -> Optional[str]:
    async with get_async_session() as db:
        return (
            await db.execute(
                select(DocumentProgress.stage).where(DocumentProgress.document_id == document_id)
            )
        ).scalar_one_or_none()


async def step(
    label: str, expected: DocumentStage, document_id: int, worker: DocumentProgressWorker
) -> bool:
    """Relance un cycle, relit l'etape, compare."""
    await worker.poll()
    obtained = await current_stage(document_id)
    ok = obtained == expected.value
    marker = "OK " if ok else "ECHEC"
    print(f"  [{marker}] {label:<38} {obtained or 'aucune ligne'}")
    return ok


async def run_scenarios(fixture: Fixture) -> int:
    # staleness a 0 : chaque appel recalcule, sans attendre les 300s par defaut.
    worker = DocumentProgressWorker(staleness_seconds=0)
    document_id = fixture.document_id
    failures = 0

    print(SEPARATOR)
    print(" Montee de la chaine")
    print(SEPARATOR)

    failures += not await step("document neuf", DocumentStage.INGESTED, document_id, worker)

    await render_pages(fixture)
    failures += not await step(
        "les pages sont rendues", DocumentStage.PAGES_RENDERED, document_id, worker
    )

    await add_ocr_result(fixture)
    failures += not await step(
        "l'OCR a produit un resultat", DocumentStage.OCR_AVAILABLE, document_id, worker
    )

    await prefill_fields(fixture)
    failures += not await step(
        "les champs sont prealimentes", DocumentStage.FIELDS_PREFILLED, document_id, worker
    )

    await submit_job(fixture)
    failures += not await step(
        f"1 job soumis sur {REQUIRED_OPERATORS}", DocumentStage.ANNOTATION, document_id, worker
    )

    await submit_job(fixture)
    failures += not await step(
        f"{REQUIRED_OPERATORS} jobs soumis sur {REQUIRED_OPERATORS}",
        DocumentStage.CONSENSUS_REACHED,
        document_id,
        worker,
    )

    print()
    print(SEPARATOR)
    print(" Retour arriere : un constat n'est pas un statut")
    print(SEPARATOR)

    await drop_jobs(fixture)
    failures += not await step(
        "les jobs disparaissent", DocumentStage.FIELDS_PREFILLED, document_id, worker
    )

    await empty_fields(fixture)
    failures += not await step(
        "les champs sont vides (lignes gardees)",
        DocumentStage.OCR_AVAILABLE,
        document_id,
        worker,
    )

    await drop_ocr(fixture)
    failures += not await step(
        "l'OCR disparait", DocumentStage.PAGES_RENDERED, document_id, worker
    )

    await unrender_pages(fixture)
    failures += not await step(
        "les pages disparaissent", DocumentStage.INGESTED, document_id, worker
    )

    print()
    print(SEPARATOR)
    print(" Garde sur required_operators")
    print(SEPARATOR)

    await set_required_operators(fixture, 0)
    failures += not await step(
        "required_operators=0, aucun job", DocumentStage.INGESTED, document_id, worker
    )

    await submit_job(fixture)
    failures += not await step(
        "required_operators=0, 1 job soumis", DocumentStage.ANNOTATION, document_id, worker
    )

    return failures


# ---------------------------------------------------------------------------
# Nettoyage
# ---------------------------------------------------------------------------


async def cleanup() -> None:
    """Supprime le jeu de demonstration, dans l'ordre des dependances."""
    async with get_async_session() as db:
        organisation_id = (
            await db.execute(select(Organisation.id).where(Organisation.slug == f"org-{MARKER}"))
        ).scalar_one_or_none()
        if organisation_id is None:
            return

        project_ids = list(
            (
                await db.execute(
                    select(Project.id).where(Project.organisation_id == organisation_id)
                )
            )
            .scalars()
            .all()
        )
        dataset_ids = list(
            (await db.execute(select(Dataset.id).where(Dataset.project_id.in_(project_ids))))
            .scalars()
            .all()
        )
        document_ids = list(
            (await db.execute(select(Document.id).where(Document.dataset_id.in_(dataset_ids))))
            .scalars()
            .all()
        )
        file_ids = list(
            (await db.execute(select(Document.file_id).where(Document.id.in_(document_ids))))
            .scalars()
            .all()
        )
        schema_ids = list(
            (await db.execute(select(DocSchema.id).where(DocSchema.project_id.in_(project_ids))))
            .scalars()
            .all()
        )

        await db.execute(delete(OcrResult).where(OcrResult.document_id.in_(document_ids)))
        await db.execute(delete(Job).where(Job.document_id.in_(document_ids)))
        await db.execute(delete(DocumentField).where(DocumentField.document_id.in_(document_ids)))
        await db.execute(
            delete(DocumentProgress).where(DocumentProgress.document_id.in_(document_ids))
        )
        await db.execute(delete(Document).where(Document.id.in_(document_ids)))
        await db.execute(delete(File).where(File.id.in_(file_ids)))
        await db.execute(delete(Dataset).where(Dataset.id.in_(dataset_ids)))
        await db.execute(delete(FieldSpec).where(FieldSpec.schema_id.in_(schema_ids)))
        await db.execute(delete(DocSchema).where(DocSchema.id.in_(schema_ids)))
        await db.execute(delete(User).where(User.organisation_id == organisation_id))
        await db.execute(delete(Project).where(Project.id.in_(project_ids)))
        await db.execute(delete(Organisation).where(Organisation.id == organisation_id))
    print("  Jeu de demonstration supprime")


# ---------------------------------------------------------------------------


async def main(keep: bool) -> int:
    init_engine(get_core_settings().async_database_url)

    # Un run precedent interrompu laisserait un slug en conflit.
    await cleanup()
    fixture = await build_fixture()
    print(f"  Document de demonstration cree (id={fixture.document_id})")
    print()

    try:
        failures = await run_scenarios(fixture)
    finally:
        print()
        if keep:
            print(f"  --keep : document {fixture.document_id} conserve en base")
        else:
            await cleanup()

    print()
    if failures:
        print(f" {failures} transition(s) en echec.")
    else:
        print(" Toutes les transitions sont conformes, dans les deux sens.")
    return 1 if failures else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transitions du DocumentProgressWorker")
    parser.add_argument("--keep", action="store_true", help="ne pas supprimer le jeu de test")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(keep=_parse_args().keep)))
