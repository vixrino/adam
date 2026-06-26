"""Jobs - tache de labellisation par operateur."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.dependencies.db import get_db
from adam_api.services.consensus import try_resolve
from adam_core.enums.states import JobState
from adam_core.enums.status import DocumentFieldStatus, DocumentStatus, JobStep
from adam_core.models import Document, DocumentField, FieldProposal, Job
from adam_core.utils.exceptions import raise_not_found, raise_unprocessable

router = APIRouter(prefix="/jobs", tags=["Jobs"])


class JobIn(BaseModel):
    dataset_id: int
    document_id: int
    agent_id: int


class FieldProposalIn(BaseModel):
    document_field_id: int
    value: str
    value_type: Optional[str] = None
    reason: Optional[str] = None


@router.get("", response_model=List[Dict[str, Any]])
async def list_jobs(
    dataset_id: Optional[int] = None,
    document_id: Optional[int] = None,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    query = select(Job)
    if dataset_id is not None:
        query = query.where(Job.dataset_id == dataset_id)
    if document_id is not None:
        query = query.where(Job.document_id == document_id)
    if state is not None:
        query = query.where(Job.state == state)
    rows = (await db.execute(query)).scalars().all()
    return [{"id": r.id, "state": r.state, "document_id": r.document_id} for r in rows]


@router.get("/{job_id}", response_model=Dict[str, Any])
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    row = await db.get(Job, job_id)
    if not row:
        raise_not_found(Job)
    return {"id": row.id, "state": row.state, "step": row.step}


@router.post("", response_model=Dict[str, Any], status_code=201)
async def create_job(body: JobIn, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    row = Job(**body.model_dump())
    db.add(row)
    await db.flush()
    return {"id": row.id, "state": row.state}


@router.post("/{job_id}/proposals", response_model=Dict[str, Any])
async def propose_field_value(
    job_id: int, body: FieldProposalIn, db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    job = await db.get(Job, job_id)
    if not job:
        raise_not_found(Job)
    if job.state != JobState.IN_PROGRESS.value:
        raise_unprocessable("Job non modifiable")
    proposal = FieldProposal(
        document_field_id=body.document_field_id,
        job_id=job_id,
        value=body.value,
        value_type=body.value_type or "TEXT",
        reason=body.reason,
        step=job.step,
    )
    db.add(proposal)
    await db.flush()
    return {"id": proposal.id, "value": proposal.value}


@router.post("/{job_id}/submit", response_model=Dict[str, Any])
async def submit_job(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    job = await db.get(Job, job_id)
    if not job:
        raise_not_found(Job)
    job.state = JobState.SUBMITTED.value
    doc = await db.get(Document, job.document_id)
    if doc and doc.status != DocumentStatus.PENDING_CONSENSUS.value:
        doc.status = DocumentStatus.PENDING_CONSENSUS.value
    await db.flush()
    background_tasks.add_task(try_resolve, job.document_id, job.dataset_id)
    return {"id": job.id, "state": job.state}
