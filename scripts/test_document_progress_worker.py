"""Test manuel de bout en bout du DocumentProgressWorker.

Le worker est un observateur : il ne fait rien avancer, il constate. Le script
fabrique donc des documents a differents stades d'avancement, fait tourner un
seul cycle, et verifie que chacun se retrouve a l'etape attendue.

Deroule
-------
1. Cree la chaine minimale en base : Organisation, Project, DocSchema, Dataset,
   FieldSpecs, puis un Document par etape de DocumentStage.
2. Appelle une seule fois DocumentProgressWorker.poll(), sans boucle infinie.
3. Relit document_progress et compare l'etape obtenue a l'etape attendue.
4. Rejoue un second cycle pour verifier l'idempotence de l'upsert.
5. Supprime tout ce qui a ete cree, sauf si --keep.

Usage
-----
    python scripts/test_document_progress_worker.py           # cycle complet
    python scripts/test_document_progress_worker.py --keep    # ne nettoie pas
    python scripts/test_document_progress_worker.py --existing  # base reelle

Le mode --existing ne cree rien et se contente de faire tourner un cycle sur les
donnees deja presentes, puis d'afficher la repartition par etape. C'est celui a
utiliser apres un seed pour voir le worker travailler sur des donnees vraies.

Prerequis : base accessible et migree (les variables POSTGRES_* du .env sont
utilisees telles quelles). La migration c3d4e5f6a7b8 cree document_progress.
"""

# pylint: disable=wrong-import-position,not-callable
# Les imports suivent le sys.path.insert ci-dessous, qui expose src/ : les
# remonter casserait le script. not-callable vise les func.* de sqlalchemy,
# construits dynamiquement (cf. document_progress_worker).

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Le script est lance depuis la racine du depot : on expose src/ au PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import delete, func, select  # noqa: E402

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

SEPARATOR = "-" * 66
MARKER = "progress-worker-test"

#: Un document par etape, avec ce qu'il faut lui donner pour l'atteindre.
#: L'ordre suit celui de DocumentStage : chaque cas ajoute au precedent.
CASES: List[Tuple[str, DocumentStage]] = [
    ("sans-pages", DocumentStage.INGESTED),
    ("pages-rendues", DocumentStage.PAGES_RENDERED),
    ("ocr-fait", DocumentStage.OCR_AVAILABLE),
    ("champs-prealimentes", DocumentStage.FIELDS_PREFILLED),
    ("annotation-en-cours", DocumentStage.ANNOTATION),
    ("consensus-atteint", DocumentStage.CONSENSUS_REACHED),
]

REQUIRED_OPERATORS = 2


# ---------------------------------------------------------------------------
# Fabrication du jeu de test
# ---------------------------------------------------------------------------


async def build_fixture() -> Dict[str, int]:
    """Cree un document par etape et renvoie {nom du cas: document_id}."""
    async with get_async_session() as db:
        organisation = Organisation(name=f"Org {MARKER}", slug=f"org-{MARKER}")
        db.add(organisation)
        await db.flush()

        user = User(
            organisation_id=organisation.id,
            email=f"{MARKER}@example.com",
            full_name="Operateur de test",
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
            document_type="PROGRESS_TEST",
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
            for i in range(4)
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

        document_ids: Dict[str, int] = {}
        for index, (case_name, _expected) in enumerate(CASES):
            payload = f"{MARKER}-{case_name}".encode()
            # page_count a 0 pour le premier cas : les pages ne sont pas rendues.
            file_row = File(
                file_path=f"/pvc/{MARKER}/{case_name}.pdf",
                storage_type="PVC",
                mime_type="application/pdf",
                page_count=0 if case_name == "sans-pages" else 2,
                file_size_bytes=len(payload),
                sha256_checksum=sha256_bytes(payload),
            )
            db.add(file_row)
            await db.flush()

            document = Document(
                dataset_id=dataset.id,
                file_id=file_row.id,
                file_name=f"{case_name}.pdf",
                status=DocumentStatus.RECEIVED.value,
            )
            db.add(document)
            await db.flush()
            document_ids[case_name] = document.id

            # A partir du 3e cas : un OcrResult.
            if index >= 2:
                db.add(
                    OcrResult(
                        document_id=document.id,
                        dataset_id=dataset.id,
                        storage_mode=StorageMode.JSONB.value,
                        raw_json={"marker": MARKER},
                    )
                )

            # A partir du 4e cas : des champs, dont deux renseignes.
            if index >= 3:
                db.add_all(
                    [
                        DocumentField(
                            document_id=document.id,
                            field_spec_id=spec.id,
                            ocr_value="valeur" if position < 2 else None,
                            status=DocumentFieldStatus.PENDING.value,
                        )
                        for position, spec in enumerate(field_specs)
                    ]
                )

            # 5e cas : un job soumis sur les deux attendus. 6e : les deux.
            submitted = 0 if index < 4 else (1 if index == 4 else REQUIRED_OPERATORS)
            db.add_all(
                [
                    Job(
                        dataset_id=dataset.id,
                        document_id=document.id,
                        agent_id=user.id,
                        state=JobState.SUBMITTED.value,
                        step=JobStep.VALIDATION.value,
                    )
                    for _ in range(submitted)
                ]
            )

        await db.flush()
        return document_ids


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


async def read_progress(document_ids: List[int]) -> Dict[int, DocumentProgress]:
    async with get_async_session() as db:
        rows = (
            (
                await db.execute(
                    select(DocumentProgress).where(DocumentProgress.document_id.in_(document_ids))
                )
            )
            .scalars()
            .all()
        )
        return {row.document_id: row for row in rows}


async def run_expected_stages() -> int:
    print(SEPARATOR)
    print(" Fabrication du jeu de test")
    print(SEPARATOR)
    document_ids = await build_fixture()
    print(f"  {len(document_ids)} documents crees, un par etape")

    print()
    print(SEPARATOR)
    print(" Cycle 1")
    print(SEPARATOR)
    await DocumentProgressWorker().poll()

    progress = await read_progress(list(document_ids.values()))
    failed = 0
    for case_name, expected in CASES:
        row = progress.get(document_ids[case_name])
        if row is None:
            print(f"  [ECHEC] {case_name:<22} aucune ligne de progression")
            failed += 1
            continue
        ok = row.stage == expected.value
        failed += 0 if ok else 1
        print(
            f"  [{'OK ' if ok else 'ECHEC'}] {case_name:<22} "
            f"attendu={expected.value:<18} obtenu={row.stage:<18} "
            f"champs={row.fields_filled}/{row.fields_total} "
            f"jobs={row.jobs_submitted}/{row.jobs_required}"
        )

    print()
    print(SEPARATOR)
    print(" Cycle 2 : idempotence")
    print(SEPARATOR)
    before = {doc_id: row.stage for doc_id, row in progress.items()}
    # staleness a 0 : toutes les lignes sont considerees perimees, donc reprises.
    await DocumentProgressWorker(staleness_seconds=0).poll()
    after = await read_progress(list(document_ids.values()))

    unchanged = all(after[doc_id].stage == stage for doc_id, stage in before.items())
    recomputed = all(
        after[doc_id].computed_at >= progress[doc_id].computed_at for doc_id in before
    )
    print(f"  [{'OK ' if unchanged else 'ECHEC'}] les etapes ne bougent pas au recalcul")
    print(f"  [{'OK ' if recomputed else 'ECHEC'}] computed_at est repousse")
    failed += 0 if unchanged else 1
    failed += 0 if recomputed else 1
    return failed


async def run_on_existing() -> int:
    """Un cycle sur les donnees deja en base, puis repartition par etape."""
    print(SEPARATOR)
    print(" Cycle sur les donnees existantes")
    print(SEPARATOR)
    await DocumentProgressWorker().poll()

    async with get_async_session() as db:
        total = (await db.execute(select(func.count()).select_from(Document))).scalar_one()
        rows = (
            await db.execute(
                select(DocumentProgress.stage, func.count())
                .group_by(DocumentProgress.stage)
                .order_by(DocumentProgress.stage)
            )
        ).all()

    covered = sum(count for _stage, count in rows)
    print(f"  {covered} document(s) couverts sur {total} en base")
    for stage, count in rows:
        print(f"    {stage:<20} {count}")
    if covered < total:
        print(
            f"  {total - covered} document(s) sans progression : "
            "relancer, le lot est plafonne a 200 par cycle."
        )
    return 0


# ---------------------------------------------------------------------------
# Nettoyage
# ---------------------------------------------------------------------------


async def cleanup() -> None:
    """Supprime tout ce que le script a cree, dans l'ordre des dependances."""
    async with get_async_session() as db:
        organisation_id = (
            await db.execute(select(Organisation.id).where(Organisation.slug == f"org-{MARKER}"))
        ).scalar_one_or_none()
        if organisation_id is None:
            return

        project_ids = (
            (await db.execute(select(Project.id).where(Project.organisation_id == organisation_id)))
            .scalars()
            .all()
        )
        dataset_ids = (
            (await db.execute(select(Dataset.id).where(Dataset.project_id.in_(project_ids))))
            .scalars()
            .all()
        )
        document_ids = (
            (await db.execute(select(Document.id).where(Document.dataset_id.in_(dataset_ids))))
            .scalars()
            .all()
        )
        file_ids = (
            (await db.execute(select(Document.file_id).where(Document.id.in_(document_ids))))
            .scalars()
            .all()
        )
        schema_ids = (
            (await db.execute(select(DocSchema.id).where(DocSchema.project_id.in_(project_ids))))
            .scalars()
            .all()
        )

        # document_progress, document_field et job partent en cascade avec le
        # document ; les autres FK sont en RESTRICT, d'ou l'ordre explicite.
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
    print("  Jeu de test supprime")


# ---------------------------------------------------------------------------


async def main(keep: bool, existing: bool) -> int:
    init_engine(get_core_settings().async_database_url)

    if existing:
        return await run_on_existing()

    # Un run precedent interrompu laisserait des lignes en conflit sur le slug.
    await cleanup()
    try:
        failed = await run_expected_stages()
    finally:
        print()
        if keep:
            print("  --keep : le jeu de test est conserve en base")
        else:
            await cleanup()

    print()
    if failed:
        print(f" {failed} verification(s) en echec.")
    else:
        print(" DocumentProgressWorker conforme.")
    return 1 if failed else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="ne pas supprimer le jeu de test")
    parser.add_argument(
        "--existing",
        action="store_true",
        help="ne rien creer, faire tourner un cycle sur les donnees en base",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    raise SystemExit(asyncio.run(main(keep=args.keep, existing=args.existing)))
