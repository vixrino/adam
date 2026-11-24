"""Creation de la ligne `user` depuis l'AD, a la premiere connexion d'un agent.

Un agent authentifie par FBI mais absent de `user` recoit un 403 sur toutes les
routes. Seul GET /users/me fait exception : si l'AD connait l'agent et que son
compte est actif, sa ligne `user` est creee, avec les droits d'un operateur sans
projet. L'affectation a un projet reste le fait d'un administrateur.

Ce que l'AD fournit, ce que la base decide
-------------------------------------------
Le matricule vient du token ; le nom, l'adresse mail et l'organisation viennent
de la fiche AD, relue par le compte de service. Le token ne dit rien de
l'organisation ni du role, et ne doit pas pouvoir le dire.

L'organisation se deduit de l'attribut `department` de la fiche, qui range la
personne dans le reseau sous la forme « RE1 US2183 DGSI DIRES SOLAPS ». Chaque
mot est compare aux slugs de la table `organisation`, sans tenir compte de la
casse ; quand plusieurs correspondent, le plus a gauche, donc le plus global
(DGSI avant DIRES), l'emporte : c'est lui qui rattache le mieux la personne. Si
aucun ne correspond, l'organisation de repli
(AD_ORGANISATION_DEFAUT) s'applique : tant que la plateforme ne compte qu'une
organisation, la Banque de France, c'est elle qui sert.

Les memes regles que pour l'affectation depuis l'annuaire valent ici : pas de
creation avec une adresse deja portee par un autre matricule (`user.email` est
unique) ; une fiche sans adresse mail recoit une adresse generee a partir du
matricule. Elles sont partagees avec routers/annuaire.py par `verifier_adresse`
et `nouvel_utilisateur`.
"""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.services.annuaire import Annuaire, PersonneAnnuaire
from adam_core.db.session import get_async_session
from adam_core.enums.status import UserStatus
from adam_core.models import Organisation, User
from adam_core.utils.logging import get_logger

logger = get_logger(__name__)

#: Un slug d'organisation ne contient que [a-z0-9-] : tout le reste separe les mots.
_SEPARATEURS = re.compile(r"[^a-z0-9\-]+")


class CreationRefusee(Exception):
    """La fiche AD ne permet pas de creer la ligne `user`."""


class SansAdresseMail(CreationRefusee):
    """Compte AD sans adresse mail : `user.email` est obligatoire."""


class AdresseMailPrise(CreationRefusee):
    """L'adresse mail de la fiche AD est deja portee par un autre matricule."""


class OrganisationInconnue(CreationRefusee):
    """Aucune organisation ne correspond au departement de la fiche AD."""


#: False : le mot le plus a gauche, donc le plus global (DGSI avant DIRES), l'emporte ; choix
#: de l'equipe. True : le plus a droite, donc le plus precis.
_PLUS_PRECIS_A_DROITE = False


def candidate_slugs(departement: Optional[str]) -> list[str]:
    """Mots du departement, en minuscules, du plus general au plus precis."""
    candidats: list[str] = []
    for mot in _SEPARATEURS.split((departement or "").lower()):
        if not mot:
            continue
        if "-" in mot:
            candidats.extend(p for p in mot.split("-") if p)
        candidats.append(mot)
    return candidats


async def department_organisation(
    db: AsyncSession, departement: Optional[str], defaut: str = ""
) -> Optional[int]:
    """Organisation non archivee dont le slug est un mot du departement (le plus global,
    cf. _PLUS_PRECIS_A_DROITE), ou a defaut celle du slug `defaut`."""
    candidats = candidate_slugs(departement)
    repli = defaut.strip().lower()
    recherches = candidats + ([repli] if repli else [])
    if not recherches:
        logger.warning("departement vide et aucune organisation par defaut configuree")
        return None
    trouvees = {
        str(slug).lower(): int(id_)
        for slug, id_ in (
            await db.execute(
                select(Organisation.slug, Organisation.id)
                .where(func.lower(Organisation.slug).in_(recherches))
                .where(Organisation.deleted_at.is_(None))
            )
        ).all()
    }
    ordre = reversed(candidats) if _PLUS_PRECIS_A_DROITE else candidats
    for slug in ordre:
        if slug in trouvees:
            return trouvees[slug]

    if repli in trouvees:
        return trouvees[repli]

    # Ni mot du departement ni repli : c'est la cause de « utilisateur non cree ». On loge ce qui
    # a ete tente (pas le matricule) pour comparer avec `SELECT slug FROM organisation`.
    logger.warning(
        "aucune organisation pour le departement [mots=%s repli=%r slugs_trouves=%s]",
        candidats,
        repli or None,
        sorted(trouvees),
    )
    return None


async def verify_address(db: AsyncSession, personne: PersonneAnnuaire) -> None:
    """Leve AdresseMailPrise si l'adresse de la fiche est deja portee par un autre matricule.

    Une fiche sans adresse n'est pas refusee : `nouvel_utilisateur` en genere une.
    """
    if not personne.email:
        logger.warning(
            "compte AD sans adresse mail [matricule=%s]",
            personne.matricule,
        )
    else:
        homonyme = (
            await db.execute(
                select(User.id).where(func.lower(User.email) == personne.email.lower())
            )
        ).first()
        if homonyme is not None:
            raise AdresseMailPrise("adresse mail deja portee par un autre utilisateur")


def new_user(personne: PersonneAnnuaire, organisation_id: int) -> User:
    """Ligne `user` d'un operateur, tiree de sa fiche AD : sans role de plateforme."""
    return User(
        organisation_id=organisation_id,
        email=personne.email if personne.email else f"{personne.matricule}@banque-france.fr",
        full_name=personne.nom_affiche,
        matricule=personne.matricule.upper(),
        status=UserStatus.ACTIVE.value,
    )


async def create_on_first_login(
    matricule: str, annuaire: Annuaire, organisation_defaut: str = ""
) -> bool:
    """Cree la ligne `user` de l'agent depuis sa fiche AD.

    Returns:
        False si l'AD ne connait pas le matricule ou que le compte est desactive.
        True si la ligne a ete creee, ou si un appel concurrent l'a creee entre-temps :
        dans les deux cas, l'appelant relit la base.

    Raises:
        AnnuaireErreur: l'AD n'a pas repondu.
        CreationRefusee: la fiche ne permet pas la creation (cf. sous-classes).
    """
    personne = await annuaire.find_person(matricule)
    if personne is None:
        return False
    try:
        async with get_async_session() as db:
            organisation_id = await department_organisation(
                db, personne.departement, organisation_defaut
            )
            if organisation_id is None:
                raise OrganisationInconnue(
                    f"aucune organisation pour le departement {personne.departement!r}"
                )
            await verify_address(db, personne)
            user = new_user(personne, organisation_id)
            db.add(user)
            await db.flush()
            logger.info(
                "utilisateur cree a sa premiere connexion [user_id=%s organisation_id=%s]",
                user.id,
                organisation_id,
            )
    except IntegrityError:
        # Deux premiers appels simultanes : le second bute sur l'unicite du
        # matricule. La ligne existe, c'est tout ce que l'appelant attend.
        # logger.info("creation concurrente a la premiere connexion : ligne relue")
        logger.exception(
            "Erreur lors de la creation du user [matricule=%s]",
            matricule,
        )
    return True
