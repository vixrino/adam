"""
scripts/show_visible_data.py
----------------------------
Ce qu'un utilisateur donne voit, projet par projet et document par document.

Complement de check_project_scoping.py, qui rend un verdict chiffre sur quatre
acteurs a la fois. Ici, un seul matricule, et des noms plutot que des
comptages : en demonstration, "il voit SUREN Cerfa mais pas Projet Temoin" se
comprend sans explication, la ou "1 projet sur 2" demande un commentaire.

Le perimetre n'est pas recalcule ici
-------------------------------------
L'organisation et le matricule a poser en session sont demandes a
_organisation_id_of et _matricule_of, les fonctions dont depend get_db. Les
reecrire donnerait un script qui montre ce qu'il croit, pas ce que l'API fait.

Le role se change a chaud
-------------------------
user_project.role est lu par une sous-requete SQL a chaque appel : le modifier
depuis pgAdmin prend effet au prochain lancement, sans redemarrer l'API. D'ou
la boucle de demonstration :

    python scripts/show_visible_data.py V654846      # BUSINESS_ADMIN : tout
    -- passer son role a OPERATOR dans pgAdmin
    python scripts/show_visible_data.py V654846      # son projet seul

Usage :
    python scripts/show_visible_data.py <matricule>
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select

from adam_api.dependencies.auth import UserCaller
from adam_api.dependencies.db import _matricule_of, _organisation_id_of
from adam_core.core.config import get_core_settings
from adam_core.db.session import get_async_session, init_engine
from adam_core.models import Document, Project, User, UserProject

SEPARATOR = "-" * 70


async def describe_user(matricule: str) -> UserCaller:
    """Identite et roles, tels que la base les porte aujourd'hui."""
    async with get_async_session() as session:
        row = (
            await session.execute(
                select(User.id, User.full_name, User.organisation_id, User.platform_role).where(
                    User.matricule == matricule
                )
            )
        ).one_or_none()
        if row is None:
            raise SystemExit(f"Matricule {matricule} absent de la base.")

        adhesions = (
            await session.execute(
                select(Project.name, UserProject.role)
                .join(UserProject, UserProject.project_id == Project.id)
                .where(UserProject.user_id == row.id)
                .order_by(Project.name)
            )
        ).all()

    print(SEPARATOR)
    print(f" {matricule} — {row.full_name}")
    print(SEPARATOR)
    print(f"  organisation_id : {row.organisation_id}")
    print(f"  platform_role   : {row.platform_role or '(aucun)'}")
    if adhesions:
        for name, role in adhesions:
            print(f"  adhesion        : {role:<15} sur {name}")
    else:
        print("  adhesion        : aucune")

    return UserCaller(
        matricule=matricule,
        organisation_id=int(row.organisation_id),
        platform_role=row.platform_role,
    )


async def show_visible(caller: UserCaller) -> None:
    """Ouvre une session scopee comme l'API le ferait, et deroule le contenu."""
    organisation_id = _organisation_id_of(caller)
    scoped_matricule = _matricule_of(caller)

    print()
    print(SEPARATOR)
    print(" Session ouverte par l'API pour cet appelant")
    print(SEPARATOR)
    print(f"  filtre organisation : {organisation_id if organisation_id else 'AUCUN'}")
    print(f"  filtre projet       : {scoped_matricule or 'AUCUN'}")
    if organisation_id is None and scoped_matricule is None:
        print("  -> role transverse : cet appelant voit toute la plateforme")

    async with get_async_session(
        organisation_id=organisation_id, matricule=scoped_matricule
    ) as session:
        projects = (await session.execute(select(Project).order_by(Project.name))).scalars().all()
        documents = (
            (await session.execute(select(Document).order_by(Document.id))).scalars().all()
        )

    print()
    print(SEPARATOR)
    print(f" Projets visibles : {len(projects)}")
    print(SEPARATOR)
    for project in projects:
        print(f"  [{project.id:>3}] {project.name}  (org {project.organisation_id})")
    if not projects:
        print("  (aucun)")

    print()
    print(SEPARATOR)
    print(f" Documents visibles : {len(documents)}")
    print(SEPARATOR)
    for document in documents:
        print(f"  [{document.id:>3}] {document.file_name:<30} {document.status}")
    if not documents:
        print("  (aucun)")


async def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage : python scripts/show_visible_data.py <matricule>")

    init_engine(get_core_settings().async_database_url)
    caller = await describe_user(sys.argv[1])
    await show_visible(caller)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
