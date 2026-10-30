"""
scripts/seed_simulation.py
--------------------------

Donnees de simulation, AJOUTEES a la base existante (aucun reset).

Cree deux projets (un par organisation) avec des utilisateurs associes, un
schema CERFA 13594 v2, deux lots (datasets) et des documents "Cerfa ..." a des
etats varies : partiellement valide, entierement valide, ERROR, litige, vierge.

Idempotent : si le projet de simulation d'une organisation existe deja, elle
est ignoree. Les documents restent en IN_PROGRESS / VALIDATED / PENDING_CONSENSUS
/ ERROR, jamais RECEIVED ni INGESTED, pour ne pas reveiller les workers.

Usage :
    python scripts/seed_simulation.py
"""

import asyncio
import hashlib
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seed import HARDCODED_FIELD_SPECS, HARDCODED_OCR_VALUES  # noqa: E402
from sqlalchemy import select  # noqa: E402

from adam_core.core.config import CoreSettings  # noqa: E402
from adam_core.db.session import get_async_session, init_engine  # noqa: E402
from adam_core.enums.ocr import OcrProvider  # noqa: E402
from adam_core.enums.roles import ProjectRole  # noqa: E402
from adam_core.enums.status import (  # noqa: E402
    DatasetStatus,
    DocumentFieldStatus as FS,
    DocumentStatus as DS,
    ProjectStatus,
    UserStatus,
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
    User,
    UserProject,
)

#: slug d'organisation -> (nom du projet, agents ; un agent existant est
#: retrouve par matricule, sinon il est cree).
PROJECTS = {
    "dgrh": (
        "Simulation - Surendettement 2026",
        [
            ("S100001", "Camille", "Lefevre", ProjectRole.BUSINESS_ADMIN),
            ("S100002", "Hugo", "Martin", ProjectRole.OPERATOR),
            ("S100003", "Lea", "Petit", ProjectRole.OPERATOR),
        ],
    ),
    "dires": (
        "Simulation - Dossiers particuliers",
        [
            ("V654846", "Philippe", "Bernard", ProjectRole.BUSINESS_ADMIN),
            ("I659418", "Nadia", "Fontaine", ProjectRole.OPERATOR),
            ("S100004", "Zoe", "Girard", ProjectRole.OPERATOR),
        ],
    ),
}

#: Etat de chaque document : (nom, prenom, cible). Deux lots par projet.
PARTIAL, COMPLETE, ERROR, DISPUTE, BLANK = "partial", "complete", "error", "dispute", "blank"
LOTS: List[Tuple[str, List[Tuple[str, str, str]]]] = [
    (
        "Lot Cerfa janvier 2026",
        [
            ("Dupont", "Jean", PARTIAL),
            ("Martin", "Sophie", COMPLETE),
            ("Bernard", "Luc", ERROR),
            ("Moreau", "Alice", BLANK),
        ],
    ),
    (
        "Lot Cerfa fevrier 2026",
        [
            ("Durand", "Paul", PARTIAL),
            ("Leroy", "Emma", COMPLETE),
            ("Garcia", "Hugo", DISPUTE),
            ("Roux", "Chloe", ERROR),
        ],
    ),
]

#: Champs dont l'OCR "se trompe" sur les documents corriges par l'operateur.
CORRECTED_KEYS = {"deposant.nom", "bien.adresse"}


async def get_or_create_user(db, org_id: int, matricule: str, first: str, last: str) -> User:
    user = (await db.execute(select(User).where(User.matricule == matricule))).scalar_one_or_none()
    if user:
        return user
    user = User(
        organisation_id=org_id,
        email=f"{first.lower()}.{last.lower()}@bdf.fr",
        full_name=f"{first} {last}",
        matricule=matricule,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.flush()
    return user


def field_rows(document_id: int, specs: List[FieldSpec], last: str, first: str, target: str):
    """DocumentField d'un document selon son etat cible."""
    rows = []
    for i, spec in enumerate(specs):
        ocr, conf, poly = HARDCODED_OCR_VALUES[spec.field_key]
        if spec.field_key == "deposant.nom":
            ocr = last.upper()
        elif spec.field_key == "deposant.prenom":
            ocr = first
        value, status, by, consensus = ocr, FS.PENDING.value, "ocr_system", False

        # Une moitie des champs traites, un litige, ou tous les champs.
        handled = target == COMPLETE or (target == PARTIAL and i < len(specs) // 2)
        if handled:
            status, consensus = FS.VALIDATED.value, True
            if spec.field_key in CORRECTED_KEYS:
                status, by = FS.CORRECTED.value, None
                ocr = ocr[:-1]  # troncature OCR, l'operateur retablit `value`
        elif target == DISPUTE:
            status, consensus = FS.VALIDATED.value, True
            if spec.field_key == "bien.valeur":
                status, consensus = FS.DISPUTED.value, False
        rows.append(
            DocumentField(
                document_id=document_id,
                field_spec_id=spec.id,
                group_id=None,
                ocr_value=ocr,
                resolved_value=value,
                status=status,
                ocr_confidence=conf,
                consensus_reached=consensus,
                ocr_polygon=poly,
                resolved_by=by,
            )
        )
    return rows


async def seed_project(db, org: Organisation, name: str, agents) -> Optional[Project]:
    exists = (
        await db.execute(
            select(Project.id).where(Project.organisation_id == org.id, Project.name == name)
        )
    ).first()
    if exists:
        print(f"  [{org.slug}] '{name}' existe deja, ignore")
        return None

    project = Project(
        organisation_id=org.id,
        name=name,
        description="Donnees de simulation",
        status=ProjectStatus.ACTIVE.value,
    )
    db.add(project)
    await db.flush()

    for matricule, first, last, role in agents:
        user = await get_or_create_user(db, org.id, matricule, first, last)
        db.add(UserProject(user_id=user.id, project_id=project.id, role=role.value))
        print(f"  [{org.slug}] {matricule} {user.full_name} -> {role.value}")

    schema = DocSchema(
        project_id=project.id,
        version=2,
        name="Schema CERFA 13594 v2",
        document_type="CERFA_13594_02",
    )
    db.add(schema)
    await db.flush()
    specs = [
        FieldSpec(
            schema_id=schema.id,
            page=page,
            section_id=sec,
            section_label=label,
            field_key=key,
            display_label=disp,
            value_type=vtype,
            required=req,
            display_order=i,
            polygon=poly,
        )
        for i, (sec, label, key, disp, vtype, page, req, poly) in enumerate(HARDCODED_FIELD_SPECS)
    ]
    db.add_all(specs)
    await db.flush()

    for lot_name, docs in LOTS:
        dataset = Dataset(
            project_id=project.id,
            schema_id=schema.id,
            name=lot_name,
            ocr_provider=OcrProvider.PULSAR.value,
            status=DatasetStatus.ACTIVE.value,
            required_operators=2,
            configs={"confidence_threshold": 0.8},
        )
        db.add(dataset)
        await db.flush()
        for last, first, target in docs:
            file_name = f"Cerfa_13594_{last}_{first}.pdf"
            path = f"/pvc/simulation/{org.slug}/{dataset.id}/{file_name}"
            file_ = File(
                file_path=path,
                storage_type="pvc",
                mime_type="application/pdf",
                page_count=2,
                file_size_bytes=120_000,
                sha256_checksum=hashlib.sha256(path.encode()).hexdigest(),
            )
            db.add(file_)
            await db.flush()
            status = {
                PARTIAL: DS.IN_PROGRESS,
                BLANK: DS.IN_PROGRESS,
                COMPLETE: DS.VALIDATED,
                DISPUTE: DS.PENDING_CONSENSUS,
                ERROR: DS.ERROR,
            }[target]
            doc = Document(
                dataset_id=dataset.id,
                file_id=file_.id,
                file_name=file_name,
                metadata_={"source": "simulation"},
                status=status.value,
            )
            db.add(doc)
            await db.flush()
            if target != ERROR:  # un document en ERROR n'a jamais ete pre-alimente
                db.add_all(field_rows(doc.id, specs, last, first, target))
            print(f"  [{org.slug}] {lot_name}: {file_name} -> {status.value}")
        await db.flush()
    return project


async def main() -> None:
    init_engine(CoreSettings().async_database_url, echo=False)
    async with get_async_session() as db:
        for slug, (name, agents) in PROJECTS.items():
            org = (
                await db.execute(select(Organisation).where(Organisation.slug == slug))
            ).scalar_one()
            await seed_project(db, org, name, agents)
    print("Simulation ajoutee")


if __name__ == "__main__":
    asyncio.run(main())
