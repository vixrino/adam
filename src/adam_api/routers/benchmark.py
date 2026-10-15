"""Benchmark OCR : recettes de test, executions et metriques, pour l'IHM.

Le parcours d'un test, tel que l'IHM le deroule :

    POST /test-recipes                     figer un lot de documents de reference
    POST /test-executions                  lancer un passage (PENDING)
    GET  /test-executions/{id}             suivre l'avancement (RUNNING...)
    GET  /test-executions/{id}/metriques   score, justes / fausses / manquees...
    GET  /test-executions/{id}/ecarts      les erreurs du moteur, champ par champ
    GET  /test-executions/comparaison      deux passages cote a cote

Le passage lui-meme est fait par le worker de benchmark : ces routes ne font
que creer, lire et calculer. Les metriques sont calculees a la lecture depuis
les comptes figes par le worker (adam_core.benchmark.metriques).

Droits : superviseurs et administrateurs NOTA, a qui le RACI confie les
recettes de tests, les campagnes et les rapports.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.dependencies.auth import UserCaller, require_user
from adam_api.dependencies.db import get_db
from adam_core.benchmark.metriques import calculer, comparer
from adam_core.enums.roles import PlatformRole
from adam_core.enums.status import TestExecutionStatus, TestRecipeStatus
from adam_core.models import (
    ComparisonResult,
    Dataset,
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


# -- Schemas ---------------------------------------------------------------------


class ConfigTest(BaseModel):
    """Configuration du test, figee avec la recette."""

    #: Score global minimal (0 a 1) pour que le passage soit « reussi ».
    score_minimal: Optional[float] = Field(default=None, ge=0, le=1)
    #: Taux d'erreur maximal par champ (cle exacte ou prefixe), pour les champs
    #: critiques : {"gestion_budget.iban": 0.0}.
    seuils_par_champ: Dict[str, float] = Field(default_factory=dict)
    #: Prefixes de cle ignores par les metriques : ["certification."].
    champs_exclus: List[str] = Field(default_factory=list)


class RecetteIn(BaseModel):
    dataset_id: int
    name: str = Field(min_length=1)
    description: Optional[str] = None
    #: Documents de reference. Vide : ceux du dataset qui portent au moins une
    #: proposition humaine, seuls a avoir une verite terrain.
    document_ids: List[int] = Field(default_factory=list)
    config: ConfigTest = Field(default_factory=ConfigTest)
    #: Figer tout de suite (une execution exige une recette figee).
    verrouiller: bool = True


class RecettePatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    document_ids: Optional[List[int]] = None
    config: Optional[ConfigTest] = None


class RecetteOut(BaseModel):
    id: int
    dataset_id: int
    name: str
    description: Optional[str] = None
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
    error_message: Optional[str] = None
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


class EcartOut(BaseModel):
    document_id: int
    field_key: str
    group_id: Optional[str] = None
    page: int
    verdict: str
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
        name=r.name,
        description=r.description,
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


# -- Recettes ------------------------------------------------------------------------


@router.get("/test-recipes", response_model=List[RecetteOut])
async def lister_recettes(
    dataset_id: Optional[int] = None,
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> List[RecetteOut]:
    requete = select(TestRecipe).order_by(TestRecipe.created_at.desc())
    if dataset_id is not None:
        requete = requete.where(TestRecipe.dataset_id == dataset_id)
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
    if await db.get(Dataset, body.dataset_id) is None:
        raise HTTPException(status_code=404, detail="Dataset introuvable")
    documents = body.document_ids or await _documents_verifies(db, body.dataset_id)
    if not documents:
        raise HTTPException(
            status_code=422,
            detail="aucun document avec une proposition humaine : sans verite terrain, "
            "il n'y a rien a mesurer",
        )
    maintenant = datetime.now(timezone.utc)
    recette = TestRecipe(
        dataset_id=body.dataset_id,
        name=body.name,
        description=body.description,
        document_ids=documents,
        config=body.config.model_dump(),
        status=(TestRecipeStatus.LOCKED if body.verrouiller else TestRecipeStatus.DRAFT).value,
        locked_at=maintenant if body.verrouiller else None,
        created_by_user_id=await _createur(db, caller),
    )
    db.add(recette)
    await db.flush()
    return _recette_out(recette)


@router.patch("/test-recipes/{recipe_id}", response_model=RecetteOut)
async def modifier_recette(
    recipe_id: int,
    body: RecettePatch,
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> RecetteOut:
    """Modifiable tant que la recette est un brouillon : une fois figee, deux
    passages ne seraient plus comparables."""
    recette = await db.get(TestRecipe, recipe_id)
    if recette is None:
        raise HTTPException(status_code=404, detail="Recette introuvable")
    if recette.status != TestRecipeStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail="recette figee : en creer une nouvelle")
    champs = body.model_dump(exclude_unset=True)
    for cle, valeur in champs.items():
        setattr(recette, cle, valeur)
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
    dataset = await db.get(Dataset, recette.dataset_id)
    execution = TestExecution(
        recipe_id=recette.id,
        status=TestExecutionStatus.PENDING.value,
        # Provisoire : le worker y recopie le moteur reellement utilise.
        ocr_provider=dataset.ocr_provider if dataset else "inconnu",
        ocr_model_id=dataset.ocr_model_id if dataset else None,
        created_by_user_id=await _createur(db, caller),
    )
    db.add(execution)
    await db.flush()
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


async def _metriques(
    db: AsyncSession, execution_id: int, tous_les_champs: bool = False
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
    lignes = (
        (
            await db.execute(
                select(EvaluationReport).where(EvaluationReport.execution_id == execution_id)
            )
        )
        .scalars()
        .all()
    )
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
    return calculer(
        [{c: getattr(rapport, c) for c in colonnes} for rapport in lignes],
        {c.name: getattr(execution, c.name) for c in TestExecution.__table__.columns},
        recette.config if recette else {},
        categories,
        tous_les_champs,
    )


@router.get("/test-executions/comparaison")
async def comparer_executions(
    a: int = Query(..., description="Execution de reference"),
    b: int = Query(..., description="Execution comparee a la reference"),
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Deux passages cote a cote ; « comparable » faux si la recette, la version
    du comparateur ou le schema different."""
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


@router.get("/test-executions/{execution_id}/metriques")
async def metriques_execution(
    execution_id: int,
    tous_les_champs: bool = Query(
        False, description="Faux : par_champ ne liste que les champs en erreur"
    ),
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Score, taux, fourchettes, decompositions par type, criticite, section,
    page et champ, verdict de la config, avertissements."""
    return await _metriques(db, execution_id, tous_les_champs)


@router.get("/test-executions/{execution_id}/ecarts", response_model=List[EcartOut])
async def ecarts_execution(
    execution_id: int,
    verdict: Optional[str] = Query(None, description="MISSING ou WRONG"),
    field_key: Optional[str] = Query(None, description="Prefixe de cle"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _: UserCaller = Depends(require_benchmark),
    db: AsyncSession = Depends(get_db),
) -> List[EcartOut]:
    """Les erreurs du moteur, champ par champ. Un champ sensible n'y montre
    jamais de valeur : seuls le verdict, la categorie et l'ampleur."""
    if await db.get(TestExecution, execution_id) is None:
        raise HTTPException(status_code=404, detail="Execution introuvable")
    cle = func.concat(FieldSpec.section_id, ".", FieldSpec.field_key)
    requete = (
        select(ComparisonResult, DocumentField, FieldSpec)
        .join(DocumentField, DocumentField.id == ComparisonResult.document_field_id)
        .join(FieldSpec, FieldSpec.id == DocumentField.field_spec_id)
        .where(ComparisonResult.execution_id == execution_id)
        .order_by(DocumentField.document_id, FieldSpec.page, FieldSpec.display_order)
        .limit(limit)
        .offset(offset)
    )
    if verdict is not None:
        requete = requete.where(ComparisonResult.verdict == verdict)
    if field_key is not None:
        requete = requete.where(
            (FieldSpec.field_key.startswith(field_key)) | (cle.startswith(field_key))
        )
    lignes = (await db.execute(requete)).all()
    return [
        EcartOut(
            document_id=df.document_id,
            field_key=(
                fs.field_key
                if fs.field_key.startswith(f"{fs.section_id}.")
                else f"{fs.section_id}.{fs.field_key}"
            ),
            group_id=df.group_id,
            page=fs.page,
            verdict=cr.verdict,
            diff_kind=cr.diff_kind,
            expected_value=cr.expected_value,
            observed_value=cr.observed_value,
            edit_distance=cr.edit_distance,
            sensitive=bool(fs.sensitive),
        )
        for cr, df, fs in lignes
    ]
