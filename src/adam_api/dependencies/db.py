"""Dependency FastAPI pour l'injection de session SQLAlchemy.

La session depend du caller resolu : c'est le point d'entree du filtrage
multi-tenant. Un UserCaller pose son ``organisation_id`` en session (le
listener do_orm_execute filtre alors toutes les tables OrganisationScoped) ;
un ServiceCaller (service machine, worker) n'impose aucun filtre. Quand le
FBI sera branche, seul le contenu de get_caller changera, pas cette chaine.

Roles de plateforme et frontiere d'organisation
-----------------------------------------------
Deux roles du RACI operent au-dessus de l'organisation : l'Administrateur NOTA,
responsable de la gestion DES organisations, et le Superviseur NOTA, responsable
des datasets de reference et des campagnes de tests sur toute la plateforme. Un
filtre derive de ``User.organisation_id`` les enfermerait dans leur propre
organisation, ce qui rendrait ces deux responsabilites inapplicables.

Leur session est donc ouverte sans organisation_id, ce qui neutralise le
listener. C'est volontairement le meme mecanisme que pour les services machine :
aucune exception n'est ajoutee au filtrage lui-meme, qui reste fail-closed par
defaut pour tout le monde.

La portee de cette neutralisation est totale : pour un porteur de role
plateforme, AUCUNE requete de l'appel HTTP n'est filtree, pas seulement celles
qui relevent de l'administration. Le cloisonnement de ces comptes repose donc
entierement sur le controle d'acces en amont, cote routes, et sur le caractere
restrictif de leur attribution. Un role plateforme accorde a tort donne acces a
l'integralite de la plateforme.

Second etage : restriction aux projets de l'appelant
-----------------------------------------------------
Le matricule est pose en session en plus de l'organisation, ce qui restreint les
tables ProjectScoped aux projets de l'appelant (cf. docstring de
adam_core.db.scoping). Les deux etages se neutralisent ensemble : un role
plateforme ou un service machine n'ouvre ni l'un ni l'autre.

Le matricule est pose pour tout utilisateur metier, Administrateur Metier
compris. Ce n'est pas ici qu'est accordee la lecture transverse que le tableau
de controle d'acces lui reconnait, mais dans member_project_ids, qui elargit le
perimetre en SQL. La raison est que le ProjectRole est porte par l'adhesion et
non par l'utilisateur : il n'est pas connu du caller, seulement de la base.
"""

from collections.abc import AsyncGenerator
from typing import Optional

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.dependencies.auth import Caller, UserCaller, get_caller
from adam_core.db.session import get_async_session
from adam_core.enums.roles import PLATFORM_ROLE_VALUES


def _organisation_id_of(caller: Caller) -> Optional[int]:
    """Organisation a scoper, ou None quand aucun filtre ne doit s'appliquer.

    None est renvoye dans deux cas : un appelant non-utilisateur (service
    machine, worker), et un utilisateur porteur d'un role de plateforme, qui
    traverse les organisations par construction (cf. docstring du module).
    """
    if isinstance(caller, UserCaller):
        if caller.platform_role in PLATFORM_ROLE_VALUES:
            return None
        return caller.organisation_id
    return None


def _matricule_of(caller: Caller) -> Optional[str]:
    """Matricule a scoper par projet, ou None quand aucun filtre ne s'applique.

    Meme logique de neutralisation que ``_organisation_id_of`` et pour les memes
    raisons : un role de plateforme traverse les projets comme il traverse les
    organisations, et un service machine n'a pas d'adhesion. Un utilisateur
    metier, lui, est restreint a ses projets quel que soit son ProjectRole.
    """
    if isinstance(caller, UserCaller):
        if caller.platform_role in PLATFORM_ROLE_VALUES:
            return None
        return caller.matricule
    return None


async def get_db(
    caller: Caller = Depends(get_caller),
) -> AsyncGenerator[AsyncSession, None]:
    async with get_async_session(
        organisation_id=_organisation_id_of(caller),
        matricule=_matricule_of(caller),
    ) as session:
        yield session
