"""Recherche dans l'annuaire AD et affectation d'une personne a un projet.

Deux routes, pour un seul geste de l'IHM : l'administrateur tape un nom, choisit
la personne dans la liste, et l'affecte au projet.

    GET  /annuaire/personnes?project_id=..&q=..   recherche dans l'AD
    POST /annuaire/affectations                   affectation par matricule

L'affectation ne fait pas confiance a ce que l'IHM renvoie de la personne :
seul le matricule est lu, et la fiche est relue dans l'AD. Si la personne n'a
pas encore de ligne `user` — elle ne s'est jamais connectee — la ligne est
creee depuis sa fiche AD, sans connexion (last_login_at vide). A sa premiere
connexion, le matricule de son token la retrouve : elle arrive deja affectee.

Droits : un administrateur NOTA (NOTA_ADMIN) partout, un administrateur metier
(BUSINESS_ADMIN) sur les projets ou il est inscrit comme tel. La recherche est
liee a un projet pour la meme raison : elle n'a de sens que pour y affecter
quelqu'un, et elle expose l'annuaire de l'entreprise.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.core.config import settings
from adam_api.dependencies.auth import UserCaller, require_user
from adam_api.dependencies.db import get_db
from adam_api.services.annuaire import (
    Annuaire,
    AnnuaireDesactive,
    AnnuaireErreur,
    LimiteurRequetes,
    PersonneAnnuaire,
    annuaire_depuis_settings,
)
from adam_api.services.premiere_connexion import (
    AdresseMailPrise,
    SansAdresseMail,
    nouvel_utilisateur,
    verifier_adresse,
)
from adam_core.enums.roles import PlatformRole, ProjectRole
from adam_core.models import Project, User, UserProject
from adam_core.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/annuaire", tags=["Annuaire"])

_limiteur = LimiteurRequetes(settings.ad_rate_seconds)


def get_annuaire() -> Annuaire:
    """Annuaire configure ; 503 s'il est desactive ou incomplet."""
    try:
        return annuaire_depuis_settings(settings)
    except AnnuaireDesactive as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def get_limiteur() -> LimiteurRequetes:
    return _limiteur


class PersonneOut(BaseModel):
    matricule: str
    nom_affiche: str
    email: Optional[str] = None
    prenom: Optional[str] = None
    nom: Optional[str] = None
    departement: Optional[str] = None
    #: La personne a deja une ligne `user` (connectee ou deja affectee ailleurs).
    deja_inscrite: bool = False
    #: La personne est deja membre du projet de la recherche.
    deja_membre: bool = False


class AffectationIn(BaseModel):
    project_id: int
    matricule: str
    role: ProjectRole = ProjectRole.OPERATOR


class AffectationOut(BaseModel):
    user_id: int
    project_id: int
    matricule: str
    role: str
    #: La ligne `user` vient d'etre creee depuis l'AD (premiere affectation).
    utilisateur_cree: bool


async def _verifier_droit(db: AsyncSession, caller: UserCaller, project_id: int) -> Project:
    """Projet vise, si l'appelant peut y affecter quelqu'un ; 404 / 403 sinon."""
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    if caller.platform_role == PlatformRole.NOTA_ADMIN.value:
        return project
    est_admin_metier = (
        await db.execute(
            select(UserProject.user_id)
            .join(User, User.id == UserProject.user_id)
            .where(func.upper(User.matricule) == caller.matricule.upper())
            .where(UserProject.project_id == project_id)
            .where(UserProject.role == ProjectRole.BUSINESS_ADMIN.value)
        )
    ).first()
    if est_admin_metier is None:
        raise HTTPException(
            status_code=403,
            detail="Reserve aux administrateurs NOTA et aux administrateurs metier du projet",
        )
    return project


@router.get("/personnes", response_model=List[PersonneOut])
async def rechercher_personnes(
    project_id: int,
    q: str = Query(..., description="Nom, prenom ou matricule, au moins quelques caracteres"),
    caller: UserCaller = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    annuaire: Annuaire = Depends(get_annuaire),
    limiteur: LimiteurRequetes = Depends(get_limiteur),
) -> List[PersonneOut]:
    """Cherche des personnes actives dans l'AD, triees par departement puis nom."""
    texte = q.strip()
    if len(texte) < settings.ad_min_chars:
        raise HTTPException(
            status_code=422,
            detail=f"au moins {settings.ad_min_chars} caracteres pour chercher dans l'annuaire",
        )
    await _verifier_droit(db, caller, project_id)
    attente = limiteur.attente(caller.matricule.upper())
    if attente > 0:
        raise HTTPException(
            status_code=429,
            detail="une recherche toutes les quelques secondes au plus",
            headers={"Retry-After": str(max(1, round(attente)))},
        )
    try:
        personnes = await annuaire.rechercher(texte)
    except AnnuaireErreur as exc:
        logger.error("recherche dans l'annuaire impossible : %s", exc)
        raise HTTPException(status_code=502, detail="annuaire injoignable") from exc

    matricules = [p.matricule.upper() for p in personnes]
    inscrits = {
        str(m).upper(): uid
        for m, uid in (
            await db.execute(
                select(User.matricule, User.id).where(func.upper(User.matricule).in_(matricules))
            )
        ).all()
    }
    membres = set()
    if inscrits:
        membres = set(
            (
                await db.execute(
                    select(UserProject.user_id)
                    .where(UserProject.project_id == project_id)
                    .where(UserProject.user_id.in_(list(inscrits.values())))
                )
            )
            .scalars()
            .all()
        )
    return [
        PersonneOut(
            **p.__dict__,
            deja_inscrite=p.matricule.upper() in inscrits,
            deja_membre=inscrits.get(p.matricule.upper()) in membres,
        )
        for p in personnes
    ]


@router.post("/affectations", response_model=AffectationOut, status_code=201)
async def affecter_depuis_annuaire(
    body: AffectationIn,
    caller: UserCaller = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    annuaire: Annuaire = Depends(get_annuaire),
) -> AffectationOut:
    """Affecte une personne de l'AD a un projet, en creant son `user` si besoin."""
    project = await _verifier_droit(db, caller, body.project_id)
    try:
        personne = await annuaire.trouver(body.matricule)
    except AnnuaireErreur as exc:
        logger.error("lecture de l'annuaire impossible : %s", exc)
        raise HTTPException(status_code=502, detail="annuaire injoignable") from exc
    if personne is None:
        raise HTTPException(
            status_code=404, detail="matricule inconnu de l'annuaire, ou compte desactive"
        )

    user, cree = await _utilisateur(db, personne, project.organisation_id)

    existante = await db.get(UserProject, (user.id, project.id))
    if existante is not None:
        raise HTTPException(
            status_code=409, detail=f"deja membre du projet (role {existante.role})"
        )
    db.add(UserProject(user_id=user.id, project_id=project.id, role=body.role.value))
    await db.flush()
    logger.info(
        "affectation depuis l'annuaire [project_id=%s user_id=%s role=%s cree=%s]",
        project.id,
        user.id,
        body.role.value,
        cree,
    )
    return AffectationOut(
        user_id=user.id,
        project_id=project.id,
        matricule=user.matricule,
        role=body.role.value,
        utilisateur_cree=cree,
    )


async def _utilisateur(
    db: AsyncSession, personne: PersonneAnnuaire, organisation_id: int
) -> tuple[User, bool]:
    """La ligne `user` de la personne, creee depuis sa fiche AD si elle manque."""
    existant = (
        await db.execute(
            select(User).where(func.upper(User.matricule) == personne.matricule.upper())
        )
    ).scalar_one_or_none()
    if existant is not None:
        if existant.organisation_id != organisation_id:
            # Un utilisateur appartient a une organisation : l'inscrire dans le
            # projet d'une autre serait une fuite entre clients.
            raise HTTPException(
                status_code=409,
                detail="cette personne appartient a une autre organisation que le projet",
            )
        return existant, False
    try:
        await verifier_adresse(db, personne)
    except SansAdresseMail as exc:
        raise HTTPException(
            status_code=422,
            detail="compte AD sans adresse mail : impossible de creer l'utilisateur",
        ) from exc
    except AdresseMailPrise as exc:
        # L'adresse est unique en base : un autre matricule la porte deja.
        raise HTTPException(
            status_code=409,
            detail="l'adresse mail de ce compte AD est deja portee par un autre utilisateur",
        ) from exc
    user = nouvel_utilisateur(personne, organisation_id)
    db.add(user)
    await db.flush()
    return user, True
