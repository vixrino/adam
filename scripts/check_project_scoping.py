"""
scripts/check_project_scoping.py
--------------------------------
Verification de bout en bout du filtrage par projet, contre une base reelle.

Les tests unitaires de tests/unit/test_project_scoping.py compilent du SQL sans
jamais l'executer : ils prouvent la forme du critere, pas qu'il ecarte une
ligne. Ce script comble l'ecart en ouvrant de vraies sessions scopees et en
comptant ce que chaque acteur voit.

Il complete le seed avec un second projet auquel l'operateur n'appartient pas,
un projet dans une autre organisation, et un Client NOTA, puis interroge la base
sous cinq identites :

    Operateur Metier      -> son projet seul
    Administrateur Metier -> les deux de son org (lecture transverse)
    Client NOTA           -> son organisation seule, jamais l'autre
    Administrateur NOTA   -> tout, session non scopee
    service machine       -> tout, session non scopee

Les matricules ne sont pas ecrits ici : chaque acteur est resolu par son role,
ce qui rend le script portable d'un environnement a l'autre (cf. le bloc de
commentaire au-dessus de NOTA_CLIENT). Les matricules retenus sont affiches en
preparation, pour qu'une resolution surprenante se voie tout de suite.

Le perimetre n'est pas ecrit en dur
------------------------------------
Chaque identite est un UserCaller passe a _organisation_id_of et _matricule_of,
les fonctions que l'API utilise reellement. Coder `counts(None, None)` pour
l'Administrateur NOTA reviendrait a supposer la decision au lieu de l'exercer :
le script afficherait OK meme si ces fonctions cessaient de neutraliser le
filtre. C'est precisement ce que le Client NOTA rend critique, lui dont le role
de plateforme ne doit PAS neutraliser quoi que ce soit.

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

from adam_api.dependencies.auth import UserCaller
from adam_api.dependencies.db import _matricule_of, _organisation_id_of
from adam_core.core.config import get_core_settings
from adam_core.db.session import get_async_session, init_engine
from adam_core.enums.ocr import OcrProvider
from adam_core.enums.roles import PlatformRole, ProjectRole
from adam_core.enums.status import DatasetStatus, DocumentStatus, ProjectStatus, UserStatus
from adam_core.models import (
    Dataset,
    DocSchema,
    Document,
    File,
    Organisation,
    Project,
    User,
    UserProject,
)
from adam_core.utils.hashing import sha256_bytes

SECOND_PROJECT = "Projet Temoin Hors Perimetre"
OTHER_ORG_PROJECT = "Projet Temoin Autre Organisation"
SEPARATOR = "-" * 60

# Les acteurs sont resolus par leur role, pas par leur matricule
# ---------------------------------------------------------------
# Ce fichier tournait sur des matricules ecrits en dur, valables pour le seul
# seed de ce depot : ailleurs, MAT00001 n'existe pas et le script s'arrete, ou
# pire, designe quelqu'un d'autre. Les intervertir inversait le verdict sans que
# rien n'echoue.
#
# Chaque acteur est donc cherche par ce qui le definit — un ProjectRole pour les
# deux acteurs metier, un PlatformRole pour les deux acteurs NOTA — en prenant
# le plus petit id pour rester deterministe s'il y a plusieurs candidats. Le
# script devient portable d'un environnement a l'autre sans edition.
#
# Une variable d'environnement force un matricule precis quand la resolution
# automatique ne convient pas :
#
#     CHECK_OPERATOR=V654846 CHECK_BUSINESS_ADMIN=I659418 \
#         python scripts/check_project_scoping.py

#: Matricule du Client NOTA cree par ce script (cf. ensure_nota_client).
NOTA_CLIENT = os.environ.get("CHECK_NOTA_CLIENT", "MAT00004")


class ActorNotFound(Exception):
    """Aucun utilisateur ne porte le role cherche : la base n'est pas seedee."""


async def matricule_with_project_role(role: str, env_var: str) -> str:
    """Matricule d'un utilisateur inscrit a un projet avec ce ProjectRole."""
    override = os.environ.get(env_var)
    if override:
        return override
    async with get_async_session() as session:
        found = (
            await session.execute(
                select(User.matricule)
                .join(UserProject, UserProject.user_id == User.id)
                .where(UserProject.role == role)
                .order_by(User.id)
                .limit(1)
            )
        ).scalar_one_or_none()
    if found is None:
        raise ActorNotFound(
            f"aucun utilisateur inscrit a un projet en {role}. "
            f"Lancer scripts/seed.py, ou forcer un matricule avec {env_var}=..."
        )
    return str(found)


async def matricule_with_platform_role(role: str, env_var: str) -> str:
    """Matricule d'un utilisateur portant ce PlatformRole."""
    override = os.environ.get(env_var)
    if override:
        return override
    async with get_async_session() as session:
        found = (
            await session.execute(
                select(User.matricule)
                .where(User.platform_role == role)
                .order_by(User.id)
                .limit(1)
            )
        ).scalar_one_or_none()
    if found is None:
        raise ActorNotFound(
            f"aucun utilisateur en {role}. "
            f"Lancer scripts/seed.py, ou forcer un matricule avec {env_var}=..."
        )
    return str(found)


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
    """Cree le Client NOTA du seed s'il manque, sans adhesion a aucun projet.

    Sans adhesion, volontairement : le Client NOTA est le commanditaire, pas un
    annotateur. Ce qu'on veut prouver n'est pas qu'il voit ses projets, mais
    qu'il ne voit jamais ceux d'une autre organisation.
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
        print(f"  Client NOTA cree ({NOTA_CLIENT}, org={organisation_id}, sans adhesion)")


async def ensure_other_org_project(own_organisation_id: int) -> None:
    """Cree un projet dans une AUTRE organisation que celle des acteurs testes.

    C'est le seul temoin capable de distinguer un role qui franchit la frontiere
    d'organisation d'un role qui ne la franchit pas. Sans lui, le Client NOTA et
    l'Administrateur NOTA verraient le meme nombre de lignes et le script ne
    prouverait rien.
    """
    async with get_async_session() as session:
        other_org_id = (
            await session.execute(
                select(Organisation.id).where(Organisation.id != own_organisation_id).limit(1)
            )
        ).scalar_one_or_none()
        if other_org_id is None:
            print("  ATTENTION : une seule organisation en base, temoin inter-org impossible")
            return

        existing = (
            await session.execute(select(Project.id).where(Project.name == OTHER_ORG_PROJECT))
        ).scalar_one_or_none()
        if existing is not None:
            print(f"  Projet d'une autre organisation deja present (id={existing})")
            return

        session.add(
            Project(
                organisation_id=other_org_id,
                name=OTHER_ORG_PROJECT,
                description="Projet hors de l'organisation des acteurs testes",
                status=ProjectStatus.ACTIVE.value,
            )
        )
        await session.flush()
        print(f"  Projet d'une autre organisation cree (org={other_org_id})")


async def counts(organisation_id: Optional[int], matricule: Optional[str]) -> tuple[int, int]:
    """Nombre de projets et de documents visibles pour cette identite."""
    async with get_async_session(organisation_id=organisation_id, matricule=matricule) as session:
        projects = (await session.execute(select(func.count()).select_from(Project))).scalar_one()
        documents = (await session.execute(select(func.count()).select_from(Document))).scalar_one()
        return projects, documents


async def counts_as(caller: UserCaller) -> tuple[int, int]:
    """Perimetre visible, en passant par les fonctions que l'API utilise.

    C'est la difference entre verifier le filtrage et verifier qu'on sait
    l'ecrire : le scope n'est pas choisi par le script mais derive du caller,
    exactement comme dans get_db.
    """
    return await counts(_organisation_id_of(caller), _matricule_of(caller))


async def caller_for(matricule: str) -> UserCaller:
    """Construit le caller depuis la base, comme le fera le FBI une fois branche."""
    async with get_async_session() as session:
        row = (
            await session.execute(
                select(User.organisation_id, User.platform_role).where(
                    User.matricule == matricule
                )
            )
        ).one()
    return UserCaller(
        matricule=matricule,
        organisation_id=int(row.organisation_id),
        platform_role=row.platform_role,
    )


async def org_of(matricule: str) -> int:
    async with get_async_session() as session:
        return (
            await session.execute(
                select(User.organisation_id).where(User.matricule == matricule)
            )
        ).scalar_one()


async def main() -> int:
    init_engine(get_core_settings().async_database_url)

    print(SEPARATOR)
    print(" Preparation")
    print(SEPARATOR)
    operator = await matricule_with_project_role(ProjectRole.OPERATOR.value, "CHECK_OPERATOR")
    business_admin = await matricule_with_project_role(
        ProjectRole.BUSINESS_ADMIN.value, "CHECK_BUSINESS_ADMIN"
    )
    nota_admin = await matricule_with_platform_role(
        PlatformRole.NOTA_ADMIN.value, "CHECK_NOTA_ADMIN"
    )
    print(f"  Operateur Metier      : {operator}")
    print(f"  Administrateur Metier : {business_admin}")
    print(f"  Administrateur NOTA   : {nota_admin}")

    organisation_id = await org_of(operator)
    await ensure_second_project(organisation_id)
    await ensure_nota_client(organisation_id)
    await ensure_other_org_project(organisation_id)

    print()
    print(SEPARATOR)
    print(" Perimetre visible par identite")
    print(SEPARATOR)

    identities = [
        ("operateur", "Operateur Metier", operator),
        ("admin_metier", "Administrateur Metier", business_admin),
        ("client", "Client NOTA", NOTA_CLIENT),
        ("admin_nota", "Administrateur NOTA", nota_admin),
    ]
    results = {key: await counts_as(await caller_for(mat)) for key, _label, mat in identities}
    results["service"] = await counts(None, None)

    for key, label, mat in identities:
        projects, documents = results[key]
        print(f"  {label:<22} ({mat:<9}) : {projects} projet(s), {documents} document(s)")
    print(
        f"  {'Service machine':<22} ({'-':<9}) : "
        f"{results['service'][0]} projet(s), {results['service'][1]} document(s)"
    )

    op_projects, op_documents = results["operateur"]
    ba_projects, ba_documents = results["admin_metier"]
    cl_projects, _cl_documents = results["client"]
    na_projects, na_documents = results["admin_nota"]
    all_projects, all_documents = results["service"]

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
            "L'Administrateur NOTA franchit la frontiere d'organisation",
            na_projects == all_projects and na_documents == all_documents,
        ),
        (
            "Le Client NOTA ne la franchit PAS",
            cl_projects < all_projects,
        ),
        (
            "Le Client NOTA, sans adhesion, ne voit aucun projet",
            cl_projects == 0,
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
