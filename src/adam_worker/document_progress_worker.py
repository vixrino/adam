"""Worker d'observation : recalcule l'avancement constate de chaque document.

Contrairement a PageImageWorker et ConsensusWorker, qui font avancer le
traitement, celui-ci ne fait avancer personne. Il regarde ou en est chaque
document — le PDF est-il la, les pages sont-elles rendues, l'OCR a-t-il produit
un resultat, combien de champs sont renseignes, combien de jobs sont soumis — et
ecrit ce constat dans document_progress. Il ne touche jamais a DOCUMENT.status,
qui reste la propriete des routes et des workers de traitement : deux ecrivains
sur la meme colonne finiraient par se contredire.

Cout du cycle
-------------
Le calcul est fait en SQL, en une requete par lot de documents plutot qu'une par
document : quatre agregats en LEFT JOIN, groupes par document. Sur un lot de 200
documents, c'est une requete, pas 800. L'ecriture est un upsert unique
(ON CONFLICT DO UPDATE sur document_id).

Choix des candidats
-------------------
Sont recalcules les documents sans ligne de progression, et ceux dont la
progression est plus vieille que `staleness_seconds`. Un document fige — archive,
exporte — repasse donc au plus une fois par periode de fraicheur, ce qui borne le
cout du polling sans avoir a tracer les modifications. C'est un compromis
assume : le worker n'est pas evenementiel, sa fraicheur vaut son intervalle.
"""

# pylint: disable=not-callable
# sqlalchemy.func fabrique ses fonctions SQL dynamiquement (func.now, func.count,
# func.coalesce, func.make_interval) : pylint n'y voit qu'un attribut de module et
# les croit non appelables. Le faux positif porte sur huit lignes du fichier, une
# desactivation au niveau module evite de le repeter a chacune.

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Dict, List, Sequence

from sqlalchemy import Select, case, func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from adam_core.db.session import get_async_session
from adam_core.enums.status import DocumentFieldStatus, DocumentStage, JobState
from adam_core.models import (
    Dataset,
    Document,
    DocumentField,
    DocumentProgress,
    File,
    Job,
    OcrResult,
)
from adam_worker.base_worker import BaseWorker

_BATCH_SIZE = 200
_DEFAULT_STALENESS_SECONDS = 300.0


class DocumentProgressWorker(BaseWorker):
    """Maintient document_progress a jour pour tous les documents."""

    poll_interval_seconds = 30.0

    def __init__(
        self,
        batch_size: int = _BATCH_SIZE,
        staleness_seconds: float = _DEFAULT_STALENESS_SECONDS,
    ) -> None:
        super().__init__()
        self.batch_size = batch_size
        self.staleness_seconds = staleness_seconds

    async def poll(self) -> None:
        async with get_async_session() as db:
            document_ids = await self._fetch_stale_document_ids(db)
            if not document_ids:
                self.logger.debug("aucun document a recalculer")
                return

            cycle_started = perf_counter()
            rows = await self._compute_progress(db, document_ids)
            await self._upsert(db, rows)

        self.logger.info(
            "avancement recalcule [documents=%s duree=%.2fs]",
            len(rows),
            perf_counter() - cycle_started,
        )

    # -- Selection des candidats -------------------------------------------

    async def _fetch_stale_document_ids(self, db: AsyncSession) -> List[int]:
        """Documents sans progression, ou dont la progression a expire."""
        cutoff = func.now() - func.make_interval(0, 0, 0, 0, 0, 0, self.staleness_seconds)
        query = (
            select(Document.id)
            .outerjoin(DocumentProgress, DocumentProgress.document_id == Document.id)
            .where(
                or_(
                    DocumentProgress.document_id.is_(None),
                    DocumentProgress.computed_at < cutoff,
                )
            )
            .order_by(Document.id)
            .limit(self.batch_size)
        )
        return list((await db.execute(query)).scalars().all())

    # -- Calcul -------------------------------------------------------------

    def _progress_query(self, document_ids: Sequence[int]) -> "Select[tuple[Any, ...]]":
        """Les quatre agregats en une requete, groupes par document.

        Les comptages passent par des sous-requetes correlees plutot que par des
        LEFT JOIN cumules : joindre document_field et job dans la meme requete
        multiplierait leurs lignes entre elles, et chaque compte serait faux du
        cardinal de l'autre.
        """
        fields_total = (
            select(func.count())
            .select_from(DocumentField)
            .where(DocumentField.document_id == Document.id)
            .scalar_subquery()
        )
        fields_filled = (
            select(func.count())
            .select_from(DocumentField)
            .where(
                DocumentField.document_id == Document.id,
                or_(
                    DocumentField.ocr_value.is_not(None),
                    DocumentField.resolved_value.is_not(None),
                ),
            )
            .scalar_subquery()
        )
        fields_validated = (
            select(func.count())
            .select_from(DocumentField)
            .where(
                DocumentField.document_id == Document.id,
                DocumentField.status == DocumentFieldStatus.VALIDATED.value,
            )
            .scalar_subquery()
        )
        jobs_submitted = (
            select(func.count())
            .select_from(Job)
            .where(
                Job.document_id == Document.id,
                Job.state == JobState.SUBMITTED.value,
            )
            .scalar_subquery()
        )
        ocr_available = (
            select(func.count())
            .select_from(OcrResult)
            .where(OcrResult.document_id == Document.id)
            .scalar_subquery()
        )

        return (
            select(
                Document.id.label("document_id"),
                File.id.is_not(None).label("pdf_received"),
                case((File.page_count > 0, True), else_=False).label("pages_rendered"),
                (ocr_available > 0).label("ocr_available"),
                fields_total.label("fields_total"),
                fields_filled.label("fields_filled"),
                fields_validated.label("fields_validated"),
                jobs_submitted.label("jobs_submitted"),
                func.coalesce(Dataset.required_operators, literal(0)).label("jobs_required"),
            )
            .select_from(Document)
            .outerjoin(File, File.id == Document.file_id)
            .outerjoin(Dataset, Dataset.id == Document.dataset_id)
            .where(Document.id.in_(document_ids))
        )

    async def _compute_progress(
        self, db: AsyncSession, document_ids: Sequence[int]
    ) -> List[Dict[str, Any]]:
        rows = (await db.execute(self._progress_query(document_ids))).all()
        return [self._to_values(row) for row in rows]

    def _to_values(self, row: "Row[Any]") -> Dict[str, Any]:
        snapshot = ProgressSnapshot(
            pages_rendered=bool(row.pages_rendered),
            ocr_available=bool(row.ocr_available),
            fields_total=row.fields_total,
            fields_filled=row.fields_filled,
            jobs_submitted=row.jobs_submitted,
            jobs_required=row.jobs_required,
        )
        return {
            "document_id": row.document_id,
            "stage": derive_stage(snapshot).value,
            "pdf_received": bool(row.pdf_received),
            "pages_rendered": bool(row.pages_rendered),
            "ocr_available": bool(row.ocr_available),
            "fields_total": row.fields_total,
            "fields_filled": row.fields_filled,
            "fields_validated": row.fields_validated,
            "jobs_submitted": row.jobs_submitted,
            "jobs_required": row.jobs_required,
        }

    # -- Ecriture -----------------------------------------------------------

    async def _upsert(self, db: AsyncSession, values: List[Dict[str, Any]]) -> None:
        """Insere ou met a jour en une passe.

        ON CONFLICT plutot qu'un SELECT suivi d'un INSERT ou d'un UPDATE : deux
        instances du worker peuvent recalculer le meme document au meme moment
        sans qu'aucune n'echoue sur une violation de cle primaire.
        """
        if not values:
            return
        statement = pg_insert(DocumentProgress).values(values)
        await db.execute(
            statement.on_conflict_do_update(
                index_elements=[DocumentProgress.document_id],
                set_={
                    column: statement.excluded[column]
                    for column in values[0]
                    if column != "document_id"
                }
                | {"computed_at": func.now()},
            )
        )


@dataclass(frozen=True)
class ProgressSnapshot:
    """Les constats d'un document, tels que lus en base.

    Regroupes en un objet plutot que passes un par un : ils voyagent toujours
    ensemble, et une signature a six parametres depassait le seuil pylint. Le
    gel evite qu'une etape de calcul ne les modifie en passant.
    """

    pages_rendered: bool
    ocr_available: bool
    fields_total: int
    fields_filled: int
    jobs_submitted: int
    jobs_required: int


def derive_stage(snapshot: ProgressSnapshot) -> DocumentStage:
    """Traduit les constats en une etape unique.

    Fonction pure, deliberement separee du worker : c'est la seule regle metier
    du module, et elle se teste sans base. L'ordre des tests suit l'ordre des
    etapes, chacune supposant les precedentes acquises.

    `pdf_received` ne figure pas dans ProgressSnapshot : un document sans ligne
    FILE reste INGESTED, qui est deja le plancher, le constat n'aurait donc
    aucun effet sur l'etape. Il est conserve comme colonne de document_progress,
    ou il distingue le document sans fichier de celui dont les pages ne sont pas
    encore rendues.

    Le consensus n'est considere atteint que si le dataset exige au moins un
    operateur : `required_operators` a zero rendrait la condition
    `jobs_submitted >= jobs_required` vraie des le depart, et tout document
    fraichement ingere serait annonce comme valide.
    """
    if 0 < snapshot.jobs_required <= snapshot.jobs_submitted:
        return DocumentStage.CONSENSUS_REACHED
    if snapshot.jobs_submitted > 0:
        return DocumentStage.ANNOTATION
    if snapshot.fields_total > 0 and snapshot.fields_filled > 0:
        return DocumentStage.FIELDS_PREFILLED
    if snapshot.ocr_available:
        return DocumentStage.OCR_AVAILABLE
    if snapshot.pages_rendered:
        return DocumentStage.PAGES_RENDERED
    return DocumentStage.INGESTED
