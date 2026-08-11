"""
scripts/check_project_scoping.py
--------------------------------
Verification de bout en bout du filtrage par projet, contre une base reelle.

Les tests unitaires de tests/unit/test_project_scoping.py compilent du SQL sans
jamais l'executer : ils prouvent la forme du critere, pas qu'il ecarte une
ligne. Ce script comble l'ecart en ouvrant de vraies sessions scopees et en
comptant ce que chaque acteur voit.

Il complete le seed avec un second projet auquel l'operateur n'appartient pas
et un Client NOTA, puis interroge la base sous cinq identites :

    MAT00002  Operateur Metier      -> son projet seul
    MAT00001  Administrateur Metier -> les deux (lecture transverse)
    MAT00004  Client NOTA           -> rien, faute d'adhesion
    MAT00003  Administrateur NOTA   -> tout, session non scopee
    (aucune)  service machine       -> tout, session non scopee

Le Client NOTA porte un role de plateforme sans franchir la frontiere
d'organisation : c'est la distinction que CROSS_ORGANISATION_ROLE_VALUES
materialise, et la seule que ce script sait mettre en evidence contre une base.

Prerequis : scripts/seed.py deja passe. Le script est idempotent et n'ecrit que
ce qui manque.

Usage :
    python scripts/check_project_scoping.py
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import func, select

from adam_core.core.config import get_core_settings
from adam_core.db.session import get_async_session, init_engine
from adam_core.enums.ocr import OcrProvider
from adam_core.enums.roles import PlatformRole
from adam_core.enums.status import DatasetStatus, DocumentStatus, ProjectStatus, UserStatus
from adam_core.models import Dataset, DocSchema, Document, File, Project, User
from adam_core.utils.hashing import sha256_bytes

SECOND_PROJECT = "Projet Temoin Hors Perimetre"
SEPARATOR = "-" * 60

# Matricules du seed, surchargeables par l'environnement. Attention a l'ordre :
# dans scripts/seed.py, MAT00001 est la variable `admin`, inscrite en
# BUSINESS_ADMIN, et MAT00002 la variable `operator`, inscrite en OPERATOR. Les
# intervertir inverse le verdict sans que rien n'echoue.
#
# Les valeurs par defaut ne valent que pour le seed de ce depot. Ailleurs :
#
#     CHECK_OPERATOR=V654846 CHECK_BUSINESS_ADMIN=I659418 \
#         python scripts/check_project_scoping.py
BUSINESS_ADMIN = os.environ.get("CHECK_BUSINESS_ADMIN", "MAT00001")
OPERATOR = os.environ.get("CHECK_OPERATOR", "MAT00002")
NOTA_ADMIN = os.environ.get("CHECK_NOTA_ADMIN", "MAT00003")

#: Client NOTA, absent du seed : ce script le cree (cf. ensure_nota_client).
NOTA_CLIENT = os.environ.get("CHECK_NOTA_CLIENT", "MAT00004")


async def ensure_second_project(organisation_id: int) -> None:
    """Cree un projet sans aucun membre, avec un document, s'il n'existe pas.

    Session non scopee volontairement : ce projet doit exister en base sans que
    personne n'y soit inscrit, c'est tout l'interet du temoin.
    """
    async with get_async_session() as session:
        existing = (
            await session.execute(select(Project.id).where(Project.name == SECOND_PROJECT))
        ).scalar_one_or_none()
        if existing is not None:
            print(f"  Projet temoin deja present (id={existing})")
            return

        project = Project(
            organisation_id=organisation_id,
            name=SECOND_PROJECT,
            description="Projet auquel l'operateur n'est pas inscrit",
            status=ProjectStatus.ACTIVE.value,
        )
        session.add(project)
        await session.flush()

        schema = DocSchema(
            project_id=project.id,
            version=1,
            name="Schema Temoin",
            document_type="TEMOIN_01",
        )
        session.add(schema)
        await session.flush()

        dataset = Dataset(
            project_id=project.id,
            schema_id=schema.id,
            name="Dataset Temoin",
            ocr_provider=OcrProvider.PULSAR.value,
            status=DatasetStatus.ACTIVE.value,
            configs={},
        )
        session.add(dataset)
        await session.flush()

        # document.file_id est NOT NULL : le fichier physique doit exister.
        payload = b"temoin"
        file_ = File(
            file_path="/pvc/temoin/temoin.pdf",
            storage_type="PVC",
            mime_type="application/pdf",
            page_count=1,
            file_size_bytes=len(payload),
            sha256_checksum=sha256_bytes(payload),
        )
        session.add(file_)
        await session.flush()

        session.add(
            Document(
                dataset_id=dataset.id,
                file_id=file_.id,
                file_name="temoin.pdf",
                status=DocumentStatus.RECEIVED.value,
            )
        )
        await session.flush()
        print(f"  Projet temoin cree (id={project.id}, 1 dataset, 1 document)")


async def ensure_nota_client(organisation_id: int) -> None:
    """Cree le Client NOTA s'il manque, sans adhesion a aucun projet.

    Sans adhesion volontairement : le Client NOTA est le commanditaire, pas un
    annotateur. Son role de plateforme ne doit pas le dispenser du filtrage,
    c'est ce que le verdict verifie.
    """
    async with get_async_session() as session:
        existing = (
            await session.execute(select(User.id).where(User.matricule == NOTA_CLIENT))
        ).scalar_one_or_none()
        if existing is not None:
            print(f"  Client NOTA deja present (id={existing})")
            return

        session.add(
            User(
                organisation_id=organisation_id,
                email="client.nota@example.com",
                full_name="Client NOTA Demo",
                matricule=NOTA_CLIENT,
                platform_role=PlatformRole.NOTA_CLIENT.value,
                status=UserStatus.ACTIVE.value,
            )
        )
        await session.flush()
        print(f"  Client NOTA cree ({NOTA_CLIENT}, sans adhesion)")


async def counts(organisation_id: Optional[int], matricule: Optional[str]) -> tuple[int, int]:
    """Nombre de projets et de documents visibles pour cette identite."""
    async with get_async_session(organisation_id=organisation_id, matricule=matricule) as session:
        projects = (await session.execute(select(func.count()).select_from(Project))).scalar_one()
        documents = (await session.execute(select(func.count()).select_from(Document))).scalar_one()
        return projects, documents


async def org_of(matricule: str) -> int:
    async with get_async_session() as session:
        found = (
            await session.execute(
                select(User.organisation_id).where(User.matricule == matricule)
            )
        ).scalar_one_or_none()
    if found is None:
        # scalar_one levait un NoResultFound qui ne nommait pas le coupable :
        # sur un seed different, le script s'arretait sans dire quoi corriger.
        raise SystemExit(
            f"Matricule {matricule} absent de la base. Lancer scripts/seed.py, "
            f"ou pointer les acteurs de ton seed :\n"
            f"  CHECK_OPERATOR=... CHECK_BUSINESS_ADMIN=... CHECK_NOTA_ADMIN=... "
            f"python scripts/check_project_scoping.py"
        )
    return int(found)


async def main() -> int:
    init_engine(get_core_settings().async_database_url)

    print(SEPARATOR)
    print(" Preparation")
    print(SEPARATOR)
    organisation_id = await org_of(OPERATOR)
    await ensure_second_project(organisation_id)
    await ensure_nota_client(organisation_id)

    print()
    print(SEPARATOR)
    print(" Perimetre visible par identite")
    print(SEPARATOR)

    results = {
        # Le matricule vient de la variable, pas du libelle : les afficher en
        # dur laissait lire "(MAT00002)" sous une session ouverte pour un tout
        # autre utilisateur, ce qui egare au pire moment, celui du diagnostic.
        f"Operateur Metier    ({OPERATOR})": await counts(organisation_id, OPERATOR),
        f"Admin Metier        ({BUSINESS_ADMIN})": await counts(
            organisation_id, BUSINESS_ADMIN
        ),
        f"Client NOTA         ({NOTA_CLIENT})": await counts(organisation_id, NOTA_CLIENT),
        f"Admin NOTA          ({NOTA_ADMIN})": await counts(None, None),
        "Service machine": await counts(None, None),
    }
    for label, (projects, documents) in results.items():
        print(f"  {label} : {projects} projet(s), {documents} document(s)")

    op_projects, op_documents = results[f"Operateur Metier    ({OPERATOR})"]
    ba_projects, ba_documents = results[f"Admin Metier        ({BUSINESS_ADMIN})"]
    cl_projects, _cl_documents = results[f"Client NOTA         ({NOTA_CLIENT})"]
    all_projects, all_documents = results["Service machine"]

    print()
    print(SEPARATOR)
    print(" Verdict")
    print(SEPARATOR)

    checks = [
        (
            "L'operateur ne voit qu'un projet sur les deux",
            op_projects == 1 and all_projects >= 2,
        ),
        (
            "L'operateur ne voit pas le document du projet temoin",
            op_documents < all_documents,
        ),
        (
            "L'Administrateur Metier voit les deux projets (lecture transverse)",
            ba_projects == all_projects,
        ),
        (
            "L'Administrateur Metier voit tous les documents",
            ba_documents == all_documents,
        ),
        (
            "La session non scopee voit tout",
            all_projects >= 2 and all_documents >= 1,
        ),
        (
            "Le Client NOTA reste filtre malgre son role de plateforme",
            cl_projects < all_projects,
        ),
    ]

    failed = 0
    for label, ok in checks:
        print(f"  [{'OK ' if ok else 'ECHEC'}] {label}")
        failed += 0 if ok else 1

    print()
    if failed:
        print(f" {failed} verification(s) en echec : le filtrage ne se comporte pas comme prevu.")
    else:
        print(" Filtrage par projet conforme.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
