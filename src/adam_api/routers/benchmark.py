"""Benchmark OCR : recettes de test, executions et metriques, pour l'IHM.

Le parcours d'un test, tel que l'IHM le deroule :

    POST /dataset-exports                  figer un lot de documents d'un dataset
    POST /test-recipes                     une recette sur cet export : documents,
                                           moteur OCR (fournisseur, modeles,
                                           consigne), seuils
    POST /test-recipes/{id}/versions       la version suivante d'une recette
    POST /test-executions                  lancer un passage (PENDING)
    GET  /test-executions/{id}             suivre l'avancement (RUNNING...)
    GET  /test-executions/{id}/metriques   score, justes / fausses / manquees...,
                                           liste des champs filtrable
    GET  /test-executions/{id}/metriques.pdf  le meme rapport en PDF, memes filtres
    GET  /test-executions/{id}/ecarts      les erreurs du moteur, document par
                                           document, pour un champ ou tous
    GET  /test-executions/comparaison      deux passages cote a cote

Le passage lui-meme est fait par le worker de benchmark : ces routes ne font
que creer, lire et calculer. Les metriques sont calculees a la lecture depuis
les comptes figes par le worker (adam_core.benchmark.metriques).

Droits : superviseurs et administrateurs NOTA, a qui le RACI confie les
recettes de tests, les campagnes et les rapports.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.core.config import settings
from adam_api.dependencies.auth import UserCaller, require_user
from adam_api.dependencies.db import get_db
from adam_api.services import rapport_metriques_pdf
from adam_core.benchmark.metriques import FiltresChamps, calculer, comparer
from adam_core.benchmark.recette import ConfigRecette, config_ocr
from adam_core.benchmark.schema import empreinte_schema, schema_en_dict
from adam_core.benchmark.verite import empreintes_documents
from adam_api.schemas.benchmark import (
    ComparaisonOut,
    ExecutionDeLExport,
    MetriquesOut,
    ProgressionOut,
)
from adam_core.enums.roles import PlatformRole
from adam_core.enums.status import ComparisonVerdict, TestExecutionStatus, TestRecipeStatus
from adam_core.models import (
    ComparisonResult,
    Dataset,
    DatasetExport,
    Document,
    DocumentField,
    EvaluationReport,
    FieldProposal,
    FieldSpec,
    TestExecution,
    TestRecipe,
    User,
)

router = APIRouter(tags=["Benchmark OCR"])

_ROLES = {PlatformRole.NOTA_SUPERVISOR.value, PlatformRole.NOTA_ADMIN.value}


async def require_benchmark(caller: UserCaller = Depends(require_user)) -> UserCaller:
    if caller.platform_role not in _ROLES:
        raise HTTPException(
            status_code=403, detail="Reserve aux superviseurs et administrateurs NOTA"
        )
    return caller


def _consigne_autorisee(caller: UserCaller, config: Optional[ConfigRecette]) -> None:
    """La consigne libre est envoyee telle quelle au modele et change ce qu'il
    lit : un superviseur pourrait fausser un benchmark sans que cela se voie.
    Reservee aux administrateurs NOTA."""
    if (
        config is not None
        and config.ocr.prompt
        and caller.platform_role != PlatformRole.NOTA_ADMIN.value
    ):
        raise HTTPException(
            status_code=403,
            detail="consigne OCR (config.ocr.prompt) reservee aux administrateurs NOTA",
        )


# -- Schemas ---------------------------------------------------------------------


class ExportIn(BaseModel):
    dataset_id: int
    name: str = Field(min_length=1)
    description: Optional[str] = None
    #: Documents a figer. Vide : ceux du dataset qui portent au moins une
    #: proposition humaine, seuls a avoir une verite terrain.
    document_ids: List[int] = Field(default_factory=list)


class ExportOut(BaseModel):
    id: int
    dataset_id: int
    schema_id: int
    schema_hash: str
    name: str
    description: Optional[str] = None
    document_ids: List[int]
    created_at: Optional[datetime] = None


class RecetteIn(BaseModel):
    dataset_export_id: int
    name: str = Field(min_length=1)
    description: Optional[str] = None
    #: Vrai : tous les documents de l'export. Faux : la liste document_ids,
    #: prise dans l'export.
    tout_l_export: bool = False
    document_ids: List[int] = Field(default_factory=list)
    config: ConfigRecette = Field(default_factory=ConfigRecette)
    #: Figer tout de suite (une execution exige une recette figee).
    verrouiller: bool = True


class RecettePatch(BaseModel):
    """Modifier un brouillon, ou decrire ce qui change dans une nouvelle version.

    Un champ absent ne change pas ; ``null`` n'est pas une valeur : il est
    refuse plutot que pris pour « faux » ou « vide ».
    """

    description: Optional[str] = None
    tout_l_export: Optional[bool] = None
    document_ids: Optional[List[int]] = None
    config: Optional[ConfigRecette] = None

    @field_validator("tout_l_export", "document_ids", "config")
    @classmethod
    def _pas_de_null(cls, valeur: Any) -> Any:
        if valeur is None:
            raise ValueError("null refuse : omettre le champ pour ne pas le changer")
        return valeur


class VersionIn(RecettePatch):
    verrouiller: bool = True


class RecetteOut(BaseModel):
    id: int
    dataset_id: int
    dataset_export_id: Optional[int] = None
    name: str
    version: int
    recette_racine_id: Optional[int] = None
    description: Optional[str] = None
    tout_l_export: bool
    document_ids: List[int]
    status: str
    config: Dict[str, Any]
    locked_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ExecutionIn(BaseModel):
    recipe_id: int


class ExecutionOut(BaseModel):
    id: int
    recipe_id: int
    status: str
    ocr_provider: str
    ocr_model_id: Optional[str] = None
    comparateur_version: Optional[str] = None
    schema_hash: Optional[str] = None
    verite_hash: Optional[str] = None
    error_message: Optional[str] = None
    documents_traites: int = 0
    documents_compared: int
    fields_compared: int
    fields_human_verified: int
    diff_count: int
    unexpected_count: int
    ocr_calls_made: int
    pages_processed: int
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


TypeErreur = Literal["fausse", "manquee", "inventee"]


class EcartOut(BaseModel):
    document_id: int
    field_key: str
    group_id: Optional[str] = None
    #: Le champ tel que /metriques le nomme (par_champ[].champ) : la cle, et la
    #: ligne pour un tableau repetable, « credits_consommation.reference[pret_7] ».
    champ: str
    page: int
    verdict: str
    #: fausse (lu, mais faux), manquee (present, non lu), inventee (lu alors
    #: que vide).
    type_erreur: TypeErreur
    diff_kind: Optional[str] = None
    #: Vides pour un champ sensible : seules l'empreinte et l'ampleur sortent.
    expected_value: Optional[str] = None
    observed_value: Optional[str] = None
    edit_distance: Optional[int] = None
    sensitive: bool


def _recette_out(r: TestRecipe) -> RecetteOut:
    return RecetteOut(
        id=r.id,
        dataset_id=r.dataset_id,
        dataset_export_id=r.dataset_export_id,
        name=r.name,
        version=r.version or 1,
        recette_racine_id=r.recette_racine_id,
        description=r.description,
        tout_l_export=bool(r.tout_l_export),
        document_ids=list(r.document_ids or []),
        status=r.status,
        config=dict(r.config or {}),
        locked_at=r.locked_at,
        created_at=r.created_at,
    )


def _execution_out(e: TestExecution) -> ExecutionOut:
    return ExecutionOut.model_validate(e, from_attributes=True)


async def _createur(db: AsyncSession, caller: UserCaller) -> int:
    user_id = (
        await db.execute(
            select(User.id).where(func.upper(User.matricule) == caller.matricule.upper())
        )
    ).scalar_one_or_none()
    if user_id is None:
        raise HTTPException(status_code=403, detail="Appelant inconnu de la table user")
    return int(user_id)


async def _documents_verifies(db: AsyncSession, dataset_id: int) -> List[int]:
    """Documents du dataset portant au moins une proposition humaine."""
    verifies = (
        select(DocumentField.document_id)
        .join(FieldProposal, FieldProposal.document_field_id == DocumentField.id)
        .distinct()
    )
    return list(
        (
            await db.execute(
                select(Document.id)
                .where(Document.dataset_id == dataset_id)
                .where(Document.id.in_(verifies))
                .order_by(Document.id)
            )
        )
        .scalars()
        .all()
    )


# -- Exports ------------------------------------------------------------------------


def _export_out(e: DatasetExport) -> ExportOut:
    return ExportOut.model_validate(e, from_attributes=True)


@router.post("/dataset-exports", response_model=ExportOut, status_code=201)
async def creer_export(
    body: ExportIn,
    caller: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> ExportOut:
    """Fige les documents d'un dataset et l'empreinte de son schema. Les
    recettes de benchmark partent d'un export, jamais du dataset vivant."""
    dataset = await db.get(Dataset, body.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset introuvable")
    if body.document_ids:
        presents = set(
            (
                await db.execute(
                    select(Document.id)
                    .where(Document.dataset_id == body.dataset_id)
                    .where(Document.id.in_(body.document_ids))
                )
            )
            .scalars()
            .all()
        )
        etrangers = sorted(set(body.document_ids) - presents)
        if etrangers:
            raise HTTPException(
                status_code=422, detail=f"documents absents du dataset : {etrangers}"
            )
        documents = sorted(set(body.document_ids))
    else:
        documents = await _documents_verifies(db, body.dataset_id)
    if not documents:
        raise HTTPException(
            status_code=422,
            detail="aucun document avec une proposition humaine : sans verite terrain, "
            "il n'y a rien a mesurer",
        )
    deja = (
        await db.execute(
            select(DatasetExport.id)
            .where(DatasetExport.dataset_id == dataset.id)
            .where(DatasetExport.name == body.name)
            .limit(1)
        )
    ).scalar_one_or_none()
    if deja is not None:
        raise HTTPException(
            status_code=409, detail=f"export « {body.name} » deja present (id {deja})"
        )
    export = DatasetExport(
        dataset_id=dataset.id,
        schema_id=dataset.schema_id,
        schema_hash=empreinte_schema(await schema_en_dict(db, dataset.schema_id)),
        verite_empreintes={
            str(d): e for d, e in (await empreintes_documents(db, documents)).items()
        },
        name=body.name,
        description=body.description,
        document_ids=documents,
        created_by_user_id=await _createur(db, caller),
    )
    await _inserer(db, export, f"export « {body.name} » deja present")
    return _export_out(export)


@router.get("/dataset-exports", response_model=List[ExportOut])
async def lister_exports(
    dataset_id: Optional[int] = None,
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> List[ExportOut]:
    requete = select(DatasetExport).order_by(DatasetExport.created_at.desc())
    if dataset_id is not None:
        requete = requete.where(DatasetExport.dataset_id == dataset_id)
    return [_export_out(e) for e in (await db.execute(requete)).scalars().all()]


@router.get("/dataset-exports/{export_id}", response_model=ExportOut)
async def lire_export(
    export_id: int,
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> ExportOut:
    export = await db.get(DatasetExport, export_id)
    if export is None:
        raise HTTPException(status_code=404, detail="Export introuvable")
    return _export_out(export)


# -- Recettes ------------------------------------------------------------------------


@router.get("/dataset-exports/{export_id}/executions", response_model=List[ExecutionDeLExport])
async def executions_de_l_export(
    export_id: int,
    limit: int = Query(50, ge=1, le=200),
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> List[ExecutionDeLExport]:
    """Les passages termines de toutes les recettes de l'export, les plus
    recents d'abord : l'ecran de comparaison y choisit deux executions a
    passer a /test-executions/comparaison."""
    await _export_de(db, export_id)
    ids = (
        (
            await db.execute(
                select(TestExecution.id)
                .join(TestRecipe, TestRecipe.id == TestExecution.recipe_id)
                .where(TestRecipe.dataset_export_id == export_id)
                .where(TestExecution.status == TestExecutionStatus.COMPLETED.value)
                .order_by(TestExecution.finished_at.desc(), TestExecution.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    lignes = []
    for execution_id in ids:
        m = await _metriques(db, execution_id)
        lignes.append(
            ExecutionDeLExport(
                execution_id=execution_id,
                recette=m["recette"],
                ocr_provider=m["execution"]["ocr_provider"],
                ocr_model_id=m["execution"]["ocr_model_id"],
                finished_at=m["execution"]["finished_at"],
                documents=m["echantillon"]["documents"],
                score=m["global"]["score"],
                taux_lectures_justes=m["global"]["taux_lectures_justes"],
                taux_valeurs_trouvees=m["global"]["taux_valeurs_trouvees"],
                taux_erreur=m["global"]["taux_erreur"],
                reussi=m["verdict"]["reussi"],
            )
        )
    return lignes


def _perimetre(export: DatasetExport, tout_l_export: bool, document_ids: List[int]) -> List[int]:
    """Les documents d'une recette : tout l'export, ou une liste prise dedans."""
    if tout_l_export:
        if document_ids:
            raise HTTPException(
                status_code=422, detail="tout_l_export et document_ids : choisir l'un ou l'autre"
            )
        return list(export.document_ids)
    if not document_ids:
        raise HTTPException(
            status_code=422, detail="document_ids vide : donner des documents ou tout_l_export"
        )
    hors_export = sorted(set(document_ids) - set(export.document_ids))
    if hors_export:
        raise HTTPException(
            status_code=422,
            detail=f"documents absents de l'export {export.id} : {hors_export}",
        )
    return sorted(set(document_ids))


def _nouveau_perimetre(
    champs: Dict[str, Any], tout_actuel: bool, liste_actuelle: List[int]
) -> Tuple[bool, List[int]]:
    """(tout_l_export, document_ids) apres un PATCH ou pour une nouvelle version.

    Meme regle des deux cotes : passer tout_l_export a faux sans liste garde
    les documents actuels (tout l'export, s'il etait pris en entier).
    """
    tout = bool(champs.get("tout_l_export", tout_actuel))
    if "document_ids" in champs:
        return tout, list(champs["document_ids"] or [])
    return tout, [] if tout else list(liste_actuelle)


def _config_resolue(config: ConfigRecette) -> Dict[str, Any]:
    """La config a figer : le moteur y est ecrit en entier.

    Les champs moteur laisses vides prennent la valeur du .env au moment de la
    creation, pas a chaque execution : une recette figee lit toujours avec le
    meme fournisseur et les memes modeles, meme si le .env change ensuite.
    La consigne vide reste vide : c'est celle du code, dont le worker note
    l'empreinte sur chaque execution.
    """
    ocr = config.ocr
    fournisseur = ocr.provider or ("MOCK" if settings.ocr_mock_enabled else "MISTRAL")
    resolu = ocr.model_copy(update={"provider": fournisseur})
    if fournisseur == "MISTRAL":
        resolu = resolu.model_copy(
            update={
                "model": ocr.model or settings.mistral_ocr_model,
                "annotation_model": ocr.annotation_model or settings.mistral_annotation_model,
            }
        )
    return config.model_copy(update={"ocr": resolu}).model_dump(exclude_none=True)


async def _inserer(db: AsyncSession, objet: Any, conflit: str) -> None:
    """Ajoute et ecrit ; un conflit d'unicite (deux creations simultanees,
    nom deja pris) rend 409 au lieu d'une erreur 500."""
    db.add(objet)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail=conflit) from exc


def _exige_un_export(recette: TestRecipe) -> None:
    """Les documents d'un benchmark viennent d'un export, jamais du dataset vivant."""
    if recette.dataset_export_id is None:
        raise HTTPException(
            status_code=409,
            detail=f"recette {recette.id} anterieure aux exports, sur le dataset vivant : "
            "creer un export (POST /dataset-exports) puis une recette dessus",
        )


async def _export_de(db: AsyncSession, export_id: Optional[int]) -> DatasetExport:
    export = await db.get(DatasetExport, export_id) if export_id is not None else None
    if export is None:
        raise HTTPException(status_code=404, detail="Export introuvable")
    return export


@router.get("/test-recipes", response_model=List[RecetteOut])
async def lister_recettes(
    dataset_id: Optional[int] = None,
    dataset_export_id: Optional[int] = None,
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> List[RecetteOut]:
    requete = select(TestRecipe).order_by(TestRecipe.created_at.desc())
    if dataset_id is not None:
        requete = requete.where(TestRecipe.dataset_id == dataset_id)
    if dataset_export_id is not None:
        requete = requete.where(TestRecipe.dataset_export_id == dataset_export_id)
    return [_recette_out(r) for r in (await db.execute(requete)).scalars().all()]


@router.get("/test-recipes/{recipe_id}", response_model=RecetteOut)
async def lire_recette(
    recipe_id: int,
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> RecetteOut:
    recette = await db.get(TestRecipe, recipe_id)
    if recette is None:
        raise HTTPException(status_code=404, detail="Recette introuvable")
    return _recette_out(recette)


@router.post("/test-recipes", response_model=RecetteOut, status_code=201)
async def creer_recette(
    body: RecetteIn,
    caller: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> RecetteOut:
    """Version 1 d'une recette, sur un export. Un nom deja pris dans le
    dataset : creer une version de la recette existante."""
    _consigne_autorisee(caller, body.config)
    export = await _export_de(db, body.dataset_export_id)
    documents = _perimetre(export, body.tout_l_export, body.document_ids)
    deja = (
        await db.execute(
            select(TestRecipe.id)
            .where(TestRecipe.dataset_id == export.dataset_id)
            .where(TestRecipe.name == body.name)
            .limit(1)
        )
    ).scalar_one_or_none()
    if deja is not None:
        raise HTTPException(
            status_code=409,
            detail=f"recette « {body.name} » deja presente (id {deja}) : "
            f"POST /test-recipes/{deja}/versions pour la faire evoluer",
        )
    maintenant = datetime.now(timezone.utc)
    recette = TestRecipe(
        dataset_id=export.dataset_id,
        dataset_export_id=export.id,
        tout_l_export=body.tout_l_export,
        name=body.name,
        version=1,
        description=body.description,
        document_ids=documents,
        config=_config_resolue(body.config),
        status=(TestRecipeStatus.LOCKED if body.verrouiller else TestRecipeStatus.DRAFT).value,
        locked_at=maintenant if body.verrouiller else None,
        created_by_user_id=await _createur(db, caller),
    )
    await _inserer(db, recette, f"recette « {body.name} » creee entre-temps : creer une version")
    return _recette_out(recette)


@router.patch("/test-recipes/{recipe_id}", response_model=RecetteOut)
async def modifier_recette(
    recipe_id: int,
    body: RecettePatch,
    caller: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> RecetteOut:
    """Modifiable tant que la recette est un brouillon : une fois figee, deux
    passages ne seraient plus comparables ; en creer une version."""
    _consigne_autorisee(caller, body.config)
    recette = await db.get(TestRecipe, recipe_id)
    if recette is None:
        raise HTTPException(status_code=404, detail="Recette introuvable")
    if recette.status != TestRecipeStatus.DRAFT.value:
        raise HTTPException(
            status_code=409,
            detail=f"recette figee : POST /test-recipes/{recipe_id}/versions pour la modifier",
        )
    _exige_un_export(recette)
    champs = body.model_dump(exclude_unset=True)
    if "tout_l_export" in champs or "document_ids" in champs:
        tout, liste = _nouveau_perimetre(
            champs, bool(recette.tout_l_export), list(recette.document_ids or [])
        )
        export = await _export_de(db, recette.dataset_export_id)
        recette.document_ids = _perimetre(export, tout, liste)
        recette.tout_l_export = tout
    if "description" in champs:
        recette.description = champs["description"]
    if body.config is not None:
        recette.config = _config_resolue(body.config)
    await db.flush()
    return _recette_out(recette)


@router.post("/test-recipes/{recipe_id}/lock", response_model=RecetteOut)
async def verrouiller_recette(
    recipe_id: int,
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> RecetteOut:
    recette = await db.get(TestRecipe, recipe_id)
    if recette is None:
        raise HTTPException(status_code=404, detail="Recette introuvable")
    if recette.status != TestRecipeStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail=f"recette deja {recette.status}")
    if not recette.document_ids:
        raise HTTPException(status_code=422, detail="recette sans document")
    recette.status = TestRecipeStatus.LOCKED.value
    recette.locked_at = datetime.now(timezone.utc)
    await db.flush()
    return _recette_out(recette)


async def _famille(db: AsyncSession, recette: TestRecipe) -> List[TestRecipe]:
    racine = recette.recette_racine_id or recette.id
    return list(
        (
            await db.execute(
                select(TestRecipe)
                .where((TestRecipe.id == racine) | (TestRecipe.recette_racine_id == racine))
                .order_by(TestRecipe.version)
            )
        )
        .scalars()
        .all()
    )


@router.post("/test-recipes/{recipe_id}/versions", response_model=RecetteOut, status_code=201)
async def nouvelle_version(
    recipe_id: int,
    body: VersionIn,
    caller: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> RecetteOut:
    """La version suivante d'une recette : meme nom, meme export, et ce que le
    corps change (documents, moteur, seuils). La recette d'origine ne bouge
    pas : ses executions restent lisibles et comparables."""
    _consigne_autorisee(caller, body.config)
    source = await db.get(TestRecipe, recipe_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Recette introuvable")
    _exige_un_export(source)
    if source.status == TestRecipeStatus.DRAFT.value:
        raise HTTPException(
            status_code=409,
            detail=f"recette {recipe_id} en brouillon : la modifier (PATCH) au lieu d'en "
            "creer une version",
        )
    famille = await _famille(db, source)
    derniere = max(famille, key=lambda r: r.version or 1)
    if derniere.id != source.id:
        raise HTTPException(
            status_code=409,
            detail=f"la derniere version est la v{derniere.version} (id {derniere.id}) : "
            f"partir d'elle, POST /test-recipes/{derniere.id}/versions",
        )
    champs = body.model_dump(exclude_unset=True)
    tout, liste = _nouveau_perimetre(
        champs, bool(source.tout_l_export), list(source.document_ids or [])
    )
    documents = _perimetre(await _export_de(db, source.dataset_export_id), tout, liste)
    config = _config_resolue(body.config) if body.config is not None else dict(source.config or {})
    maintenant = datetime.now(timezone.utc)
    version = TestRecipe(
        dataset_id=source.dataset_id,
        dataset_export_id=source.dataset_export_id,
        tout_l_export=tout,
        name=source.name,
        version=(derniere.version or 1) + 1,
        recette_racine_id=source.recette_racine_id or source.id,
        description=champs.get("description", source.description),
        document_ids=documents,
        config=config,
        status=(TestRecipeStatus.LOCKED if body.verrouiller else TestRecipeStatus.DRAFT).value,
        locked_at=maintenant if body.verrouiller else None,
        created_by_user_id=await _createur(db, caller),
    )
    await _inserer(
        db, version, f"une version de « {source.name} » a ete creee entre-temps : reessayer"
    )
    return _recette_out(version)


@router.get("/test-recipes/{recipe_id}/versions", response_model=List[RecetteOut])
async def lister_versions(
    recipe_id: int,
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> List[RecetteOut]:
    """Toutes les versions de la recette, de la premiere a la derniere."""
    recette = await db.get(TestRecipe, recipe_id)
    if recette is None:
        raise HTTPException(status_code=404, detail="Recette introuvable")
    return [_recette_out(r) for r in await _famille(db, recette)]


# -- Executions ----------------------------------------------------------------------


@router.post("/test-executions", response_model=ExecutionOut, status_code=201)
async def lancer_execution(
    body: ExecutionIn,
    caller: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> ExecutionOut:
    """Cree un passage en attente ; le worker de benchmark le prend."""
    recette = await db.get(TestRecipe, body.recipe_id)
    if recette is None:
        raise HTTPException(status_code=404, detail="Recette introuvable")
    if recette.status != TestRecipeStatus.LOCKED.value:
        raise HTTPException(
            status_code=409, detail="recette non figee : la verrouiller avant de la lancer"
        )
    _exige_un_export(recette)
    moteur = config_ocr(recette.config)
    execution = TestExecution(
        recipe_id=recette.id,
        status=TestExecutionStatus.PENDING.value,
        # Provisoire : le worker y recopie le moteur reellement utilise.
        ocr_provider=moteur.provider or "EN_ATTENTE",
        ocr_model_id=moteur.model,
        created_by_user_id=await _createur(db, caller),
    )
    db.add(execution)
    await db.flush()
    return _execution_out(execution)


_EN_COURS = (TestExecutionStatus.PENDING.value, TestExecutionStatus.RUNNING.value)


@router.get("/test-executions/{execution_id}/progression", response_model=ProgressionOut)
async def progression_execution(
    execution_id: int,
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> ProgressionOut:
    """Avancement d'un passage, a interroger toutes les quelques secondes.

    Le worker ecrit ses compteurs a chaque document : la progression avance
    document par document, pas champ par champ. L'estimation de fin suppose
    des documents de meme taille."""
    execution = await db.get(TestExecution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution introuvable")
    recette = await db.get(TestRecipe, execution.recipe_id)
    total = len(getattr(recette, "document_ids", None) or [])
    traites = int(execution.documents_traites or 0)
    statut = execution.status
    if statut == TestExecutionStatus.COMPLETED.value:
        pourcentage = 100.0
    else:
        pourcentage = round(min(traites / total, 1.0) * 100, 1) if total else 0.0
    ecoule = restant = None
    if execution.started_at is not None:
        fin = execution.finished_at or datetime.now(timezone.utc)
        ecoule = round((fin - execution.started_at).total_seconds(), 1)
        if statut == TestExecutionStatus.RUNNING.value and 0 < traites < total:
            restant = round(ecoule / traites * (total - traites), 1)
    return ProgressionOut(
        execution_id=execution.id,
        status=statut,
        termine=statut not in _EN_COURS,
        annulable=statut in _EN_COURS,
        documents_total=total,
        documents_traites=traites,
        documents_compares=int(execution.documents_compared or 0),
        pourcentage=pourcentage,
        champs_compares=int(execution.fields_compared or 0),
        ecarts=int(execution.diff_count or 0),
        appels_ocr=int(execution.ocr_calls_made or 0),
        pages_traitees=int(execution.pages_processed or 0),
        secondes_ecoulees=ecoule,
        secondes_restantes_estimees=restant,
        dernier_signe_de_vie=execution.updated_at,
        message=execution.error_message,
    )


@router.post("/test-executions/{execution_id}/cancel", response_model=ExecutionOut)
async def annuler_execution(
    execution_id: int,
    caller: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> ExecutionOut:
    """Arrete un passage en attente ou en cours.

    En attente, il ne demarrera pas. En cours, le worker s'arrete avant le
    document suivant : celui qu'il lit va au bout (ses appels OCR sont deja
    partis). Les ecarts deja ecrits restent ; pas de metriques, le passage est
    incomplet. Une seule instruction conditionnelle : un passage termine entre
    la lecture et l'annulation n'est pas ecrase."""
    annulee = (
        await db.execute(
            update(TestExecution)
            .where(TestExecution.id == execution_id)
            .where(TestExecution.status.in_(_EN_COURS))
            .values(
                status=TestExecutionStatus.CANCELLED.value,
                finished_at=datetime.now(timezone.utc),
                error_message=f"annulee par {caller.matricule}",
            )
            .returning(TestExecution.id)
        )
    ).scalar_one_or_none()
    execution = await db.get(TestExecution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution introuvable")
    if annulee is None:
        raise HTTPException(
            status_code=409, detail=f"execution {execution.status} : plus rien a annuler"
        )
    await db.refresh(execution)
    return _execution_out(execution)


@router.get("/test-executions", response_model=List[ExecutionOut])
async def lister_executions(
    recipe_id: Optional[int] = None,
    status: Optional[str] = None,
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> List[ExecutionOut]:
    requete = select(TestExecution).order_by(TestExecution.created_at.desc())
    if recipe_id is not None:
        requete = requete.where(TestExecution.recipe_id == recipe_id)
    if status is not None:
        requete = requete.where(TestExecution.status == status)
    return [_execution_out(e) for e in (await db.execute(requete)).scalars().all()]


def filtres_champs(
    recherche: Optional[str] = Query(None, description="Morceau de la cle du champ"),
    type_champ: List[str] = Query([], description="TEXT, NUMBER, DATE, BOOLEAN ; repetable"),
    reussite_inferieure_a: Optional[float] = Query(
        None, ge=0, le=1, description="Reussite strictement inferieure (0 a 1)"
    ),
    type_erreur: List[TypeErreur] = Query([], description="Au moins une erreur de ce type"),
    section: List[str] = Query([], description="section_id ; repetable"),
) -> FiltresChamps:
    """Filtres de la liste des champs, partages par la page et le PDF."""
    return FiltresChamps(
        recherche=recherche.strip() if recherche and recherche.strip() else None,
        types_champ=tuple(type_champ),
        reussite_inferieure_a=reussite_inferieure_a,
        types_erreur=tuple(type_erreur),
        sections=tuple(section),
    )


async def _metriques(
    db: AsyncSession,
    execution_id: int,
    tous_les_champs: bool = False,
    filtres: Optional[FiltresChamps] = None,
) -> Dict[str, Any]:
    execution = await db.get(TestExecution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} introuvable")
    if execution.status != TestExecutionStatus.COMPLETED.value:
        raise HTTPException(
            status_code=409,
            detail=f"execution {execution_id} {execution.status} : metriques disponibles "
            "une fois COMPLETED",
        )
    recette = await db.get(TestRecipe, execution.recipe_id)
    # Le libelle de section du schema (« Co-deposant ») accompagne l'id fige
    # (co_deposant) : c'est lui qu'affichent la page et le PDF.
    lignes = (
        await db.execute(
            select(EvaluationReport, FieldSpec.section_label)
            .outerjoin(FieldSpec, FieldSpec.id == EvaluationReport.field_spec_id)
            .where(EvaluationReport.execution_id == execution_id)
        )
    ).all()
    categories = {
        str(kind or verdict): int(n)
        for kind, verdict, n in (
            await db.execute(
                select(ComparisonResult.diff_kind, ComparisonResult.verdict, func.count())
                .where(ComparisonResult.execution_id == execution_id)
                .group_by(ComparisonResult.diff_kind, ComparisonResult.verdict)
            )
        ).all()
    }
    colonnes = [c.name for c in EvaluationReport.__table__.columns]
    metriques = calculer(
        [
            {**{c: getattr(rapport, c) for c in colonnes}, "section_label": libelle}
            for rapport, libelle in lignes
        ],
        {c.name: getattr(execution, c.name) for c in TestExecution.__table__.columns},
        recette.config if recette else {},
        categories,
        tous_les_champs,
        filtres,
    )
    # Pour l'en-tete « Dataset X · recette #3 », sans deux appels de plus.
    dataset = await db.get(Dataset, recette.dataset_id) if recette else None
    # Le perimetre de la recette : comparer() en deduit si deux executions de
    # recettes differentes ont lu les memes documents.
    metriques["recette"] = {
        "id": execution.recipe_id,
        "name": getattr(recette, "name", None),
        "version": getattr(recette, "version", None) or 1,
        "dataset_export_id": getattr(recette, "dataset_export_id", None),
        "document_ids": sorted(getattr(recette, "document_ids", None) or []),
    }
    metriques["dataset"] = {
        "id": getattr(recette, "dataset_id", None),
        "name": getattr(dataset, "name", None),
    }
    return metriques


@router.get("/test-executions/comparaison", response_model=ComparaisonOut)
async def comparer_executions(
    a: int = Query(..., description="Execution de reference"),
    b: int = Query(..., description="Execution comparee a la reference"),
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Deux passages cote a cote, de la meme recette ou de deux recettes sur le
    meme export (deux moteurs OCR). « comparable » faux si les documents, la
    version du comparateur, le schema ou la verite humaine different ;
    ``moteur`` dit ce qui change entre a et b."""
    return comparer(await _metriques(db, a, True), await _metriques(db, b, True))


@router.get("/test-executions/{execution_id}", response_model=ExecutionOut)
async def lire_execution(
    execution_id: int,
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> ExecutionOut:
    execution = await db.get(TestExecution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution introuvable")
    return _execution_out(execution)


@router.get("/test-executions/{execution_id}/metriques", response_model=MetriquesOut)
async def metriques_execution(
    execution_id: int,
    tous_les_champs: bool = Query(
        False, description="Faux : par_champ ne liste que les champs en erreur"
    ),
    filtres: FiltresChamps = Depends(filtres_champs),
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Score, taux, fourchettes, decompositions par type, criticite, section,
    page et champ, verdict de la config, avertissements.

    Chaque champ porte sa reussite, ses documents en erreur et son echec
    principal. Les filtres ne restreignent que ``par_champ`` ; ``selection``
    rappelle les filtres et compte les champs retenus."""
    return await _metriques(db, execution_id, tous_les_champs, filtres)


@router.get(
    "/test-executions/{execution_id}/metriques.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Le rapport en PDF"}},
)
async def metriques_pdf(
    execution_id: int,
    filtres: FiltresChamps = Depends(filtres_champs),
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Le rapport de qualite d'extraction en PDF, avec les filtres de la page :
    taux et marge, repartition, filtres appliques, champs en erreur, extraits
    des documents en erreur. Un champ sensible n'y montre jamais de valeur."""
    metriques = await _metriques(db, execution_id, False, filtres)
    extraits = {
        champ: rapport_metriques_pdf.dict_ecarts(
            await lire_ecarts(
                db,
                execution_id,
                champs=[champ],
                types_erreur=list(filtres.types_erreur),
                limit=rapport_metriques_pdf.EXTRAITS_PAR_CHAMP,
            )
        )
        for champ in rapport_metriques_pdf.extraits_a_montrer(metriques["par_champ"])
    }
    pdf = await run_in_threadpool(
        rapport_metriques_pdf.rendre_pdf,
        metriques,
        recette=metriques["recette"],
        dataset=metriques["dataset"]["name"],
        extraits=extraits,
        edite_le=datetime.now(timezone.utc),
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="rapport-test-{execution_id}.pdf"'},
    )


_CHAMP = re.compile(r"^(?P<cle>[^\[\]]+)(?:\[(?P<ligne>[^\[\]]+)\])?$")


def _decouper_champ(champ: str) -> Tuple[str, Optional[str]]:
    """« section.cle[ligne] » -> (« section.cle », « ligne ») ; 422 si illisible."""
    trouve = _CHAMP.match(champ.strip())
    if trouve is None:
        raise HTTPException(
            status_code=422, detail="champ attendu sous la forme section.cle ou section.cle[ligne]"
        )
    return trouve["cle"], trouve["ligne"]


def _requete_ecarts(
    execution_id: int,
    *,
    verdict: Optional[str] = None,
    field_key: Optional[str] = None,
    champs: Optional[List[str]] = None,
    types_erreur: Optional[List[str]] = None,
) -> Any:
    """La requete des ecarts filtres, sans ordre ni pagination.

    Le type d'erreur se deduit de la valeur attendue : vide, le moteur l'a
    inventee. Un champ sensible ne stocke pas cette valeur ; elle est alors lue
    dans la verite (document_field.resolved_value), pour savoir si elle est
    vide, et n'est jamais renvoyee.
    """
    cle = func.concat(FieldSpec.section_id, ".", FieldSpec.field_key)
    attendu = case(
        (FieldSpec.sensitive.is_(True), DocumentField.resolved_value),
        else_=ComparisonResult.expected_value,
    )
    type_erreur = case(
        (ComparisonResult.verdict == ComparisonVerdict.MISSING.value, "manquee"),
        (func.trim(func.coalesce(attendu, "")) == "", "inventee"),
        else_="fausse",
    )
    requete = (
        select(ComparisonResult, DocumentField, FieldSpec, type_erreur)
        .join(DocumentField, DocumentField.id == ComparisonResult.document_field_id)
        .join(FieldSpec, FieldSpec.id == DocumentField.field_spec_id)
        .where(ComparisonResult.execution_id == execution_id)
    )
    if verdict is not None:
        requete = requete.where(ComparisonResult.verdict == verdict)
    if field_key is not None:
        requete = requete.where(
            (FieldSpec.field_key.startswith(field_key)) | (cle.startswith(field_key))
        )
    if champs:
        conditions = []
        for champ in champs:
            cle_champ, ligne = _decouper_champ(champ)
            conditions.append(
                and_(
                    (FieldSpec.field_key == cle_champ) | (cle == cle_champ),
                    (
                        DocumentField.group_id == ligne
                        if ligne
                        else DocumentField.group_id.is_(None)
                    ),
                )
            )
        requete = requete.where(or_(*conditions))
    if types_erreur:
        requete = requete.where(type_erreur.in_(types_erreur))
    return requete


async def lire_ecarts(
    db: AsyncSession,
    execution_id: int,
    *,
    limit: Optional[int] = 100,
    offset: int = 0,
    **filtres: Any,
) -> List[EcartOut]:
    """Les ecarts d'une execution, document par document (filtres de
    _requete_ecarts : verdict, field_key, champs, types_erreur)."""
    requete = (
        _requete_ecarts(execution_id, **filtres)
        .order_by(
            DocumentField.document_id,
            FieldSpec.page,
            FieldSpec.display_order,
            ComparisonResult.id,
        )
        .offset(offset)
    )
    if limit is not None:
        requete = requete.limit(limit)
    lignes = (await db.execute(requete)).all()
    return [_ecart_out(cr, df, fs, str(type_)) for cr, df, fs, type_ in lignes]


async def compter_ecarts(db: AsyncSession, execution_id: int, **filtres: Any) -> int:
    """Nombre d'ecarts avec les memes filtres : le N de « Document i sur N »."""
    requete = select(func.count()).select_from(_requete_ecarts(execution_id, **filtres).subquery())
    return int((await db.execute(requete)).scalar_one())


def _ecart_out(cr: ComparisonResult, df: DocumentField, fs: FieldSpec, type_: str) -> EcartOut:
    field_key = (
        fs.field_key
        if fs.field_key.startswith(f"{fs.section_id}.")
        else f"{fs.section_id}.{fs.field_key}"
    )
    return EcartOut(
        document_id=df.document_id,
        field_key=field_key,
        group_id=df.group_id,
        champ=f"{field_key}[{df.group_id}]" if df.group_id else field_key,
        page=fs.page,
        verdict=cr.verdict,
        type_erreur=cast(TypeErreur, type_),
        diff_kind=cr.diff_kind,
        expected_value=cr.expected_value,
        observed_value=cr.observed_value,
        edit_distance=cr.edit_distance,
        sensitive=bool(fs.sensitive),
    )


@router.get("/test-executions/{execution_id}/ecarts", response_model=List[EcartOut])
async def ecarts_execution(
    execution_id: int,
    reponse: Response,
    verdict: Optional[str] = Query(None, description="MISSING ou WRONG"),
    field_key: Optional[str] = Query(None, description="Prefixe de cle"),
    champ: List[str] = Query(
        [], description="Champ exact, tel que par_champ[].champ le nomme ; repetable"
    ),
    type_erreur: List[TypeErreur] = Query([], description="fausse, manquee, inventee"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> List[EcartOut]:
    """Les erreurs du moteur, document par document. Avec ``champ`` : les
    documents ou ce champ est en erreur, pour les parcourir un a un.
    L'en-tete X-Total-Count donne leur nombre, toutes pages confondues.

    Un champ sensible n'y montre jamais de valeur : seuls le verdict, le type
    d'erreur, la categorie et l'ampleur."""
    if await db.get(TestExecution, execution_id) is None:
        raise HTTPException(status_code=404, detail="Execution introuvable")
    filtres: Dict[str, Any] = {
        "verdict": verdict,
        "field_key": field_key,
        "champs": champ,
        "types_erreur": list(type_erreur),
    }
    reponse.headers["X-Total-Count"] = str(await compter_ecarts(db, execution_id, **filtres))
    return await lire_ecarts(db, execution_id, limit=limit, offset=offset, **filtres)
