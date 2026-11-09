"""Benchmark OCR : recettes de test, executions et metriques, pour l'IHM.

Le parcours d'un test, tel que l'IHM le deroule :

    POST /test-recipes                     figer un lot de documents de reference
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
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.dependencies.auth import UserCaller, require_user
from adam_api.dependencies.db import get_db
from adam_api.services import rapport_metriques_pdf
from adam_core.benchmark.metriques import FiltresChamps, calculer, comparer
from adam_core.enums.roles import PlatformRole
from adam_core.enums.status import ComparisonVerdict, TestExecutionStatus, TestRecipeStatus
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
        filtres,
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
    execution = await db.get(TestExecution, execution_id)
    recette = await db.get(TestRecipe, execution.recipe_id) if execution else None
    dataset = await db.get(Dataset, recette.dataset_id) if recette else None
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
        recette={
            "id": execution.recipe_id if execution else None,
            "name": getattr(recette, "name", None),
        },
        dataset=getattr(dataset, "name", None),
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


async def lire_ecarts(
    db: AsyncSession,
    execution_id: int,
    *,
    verdict: Optional[str] = None,
    field_key: Optional[str] = None,
    champs: Optional[List[str]] = None,
    types_erreur: Optional[List[str]] = None,
    limit: Optional[int] = 100,
    offset: int = 0,
) -> List[EcartOut]:
    """Les ecarts d'une execution, document par document.

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
    lignes = (await db.execute(requete)).all()
    return [_ecart_out(cr, df, fs, str(type_)) for cr, df, fs, type_ in lignes]


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

    Un champ sensible n'y montre jamais de valeur : seuls le verdict, le type
    d'erreur, la categorie et l'ampleur."""
    if await db.get(TestExecution, execution_id) is None:
        raise HTTPException(status_code=404, detail="Execution introuvable")
    return await lire_ecarts(
        db,
        execution_id,
        verdict=verdict,
        field_key=field_key,
        champs=champ,
        types_erreur=list(type_erreur),
        limit=limit,
        offset=offset,
    )
