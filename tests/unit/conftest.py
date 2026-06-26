"""Fixtures partagées et factories de mocks pour tous les tests unitaires."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from adam_api.dependencies.db import get_db
from adam_api.main import app

NOW = datetime(2026, 6, 26, 12, 0, 0, tzinfo=timezone.utc)
SHA256 = "a" * 64


# ---------------------------------------------------------------------------
# Helpers — résultats SQLAlchemy mockés
# ---------------------------------------------------------------------------


def make_result(rows=None, single=None, scalar=0):
    """Crée un MagicMock imitant un SQLAlchemy CursorResult."""
    r = MagicMock()
    r.scalars.return_value.all.return_value = rows if rows is not None else []
    r.scalar_one_or_none.return_value = single
    r.scalar_one.return_value = scalar
    return r


# ---------------------------------------------------------------------------
# Factories — objets ORM mockés
# ---------------------------------------------------------------------------


def fake_file(**kw):
    """File ORM mock — tous les attributs sont typés explicitement."""
    f = MagicMock()
    f.id = kw.get("id", 1)
    f.file_path = kw.get("file_path", "/pvc/test.pdf")
    f.sha256_checksum = kw.get("sha256_checksum", SHA256)
    f.file_size_bytes = kw.get("file_size_bytes", 2048)
    f.page_count = kw.get("page_count", 4)
    f.mime_type = kw.get("mime_type", "application/pdf")
    f.storage_type = kw.get("storage_type", "pvc")
    f.created_at = kw.get("created_at", NOW)
    f.documents = kw.get("documents", [])
    return f


def fake_doc(**kw):
    """Document ORM mock — inclut page_count pour satisfaire DocumentOut."""
    doc = MagicMock()
    doc.id = kw.get("id", 1)
    doc.dataset_id = kw.get("dataset_id", 1)
    doc.file_id = kw.get("file_id", 1)
    doc.file_name = kw.get("file_name", "test.pdf")
    doc.status = kw.get("status", "RECEIVED")
    doc.metadata_ = kw.get("metadata_", None)
    doc.image_paths = kw.get("image_paths", None)
    doc.page_count = kw.get("page_count", 4)
    doc.file = kw.get("file", fake_file())
    doc.document_fields = kw.get("document_fields", [])
    doc.ocr_results = kw.get("ocr_results", [])
    doc.jobs = kw.get("jobs", [])
    return doc


def fake_dataset(**kw):
    """Dataset ORM mock."""
    ds = MagicMock()
    ds.id = kw.get("id", 1)
    ds.project_id = kw.get("project_id", 10)
    ds.schema_id = kw.get("schema_id", 5)
    ds.name = kw.get("name", "Dataset Test")
    ds.description = kw.get("description", None)
    ds.status = kw.get("status", "ACTIVE")
    ds.ocr_provider = kw.get("ocr_provider", "PULSAR")
    ds.required_operators = kw.get("required_operators", 3)
    ds.ocr_job_enabled = kw.get("ocr_job_enabled", True)
    return ds


def fake_field_spec(**kw):
    """FieldSpec ORM mock."""
    fs = MagicMock()
    fs.section_id = kw.get("section_id", "s1")
    fs.section_label = kw.get("section_label", "Section 1")
    fs.field_key = kw.get("field_key", "nom")
    fs.page = kw.get("page", 1)
    return fs


def fake_document_field(**kw):
    """DocumentField ORM mock — attributs compatibles avec DocumentFieldOut."""
    df = MagicMock()
    df.id = kw.get("id", 1)
    df.document_id = kw.get("document_id", 1)
    df.field_spec_id = kw.get("field_spec_id", 1)
    df.group_id = kw.get("group_id", None)
    df.ocr_value = kw.get("ocr_value", None)
    df.resolved_value = kw.get("resolved_value", None)
    df.status = kw.get("status", "PENDING")
    df.ocr_confidence = kw.get("ocr_confidence", None)
    df.consensus_reached = kw.get("consensus_reached", False)
    df.ocr_polygon = kw.get("ocr_polygon", None)
    df.field_spec = kw.get("field_spec", fake_field_spec(**kw))
    return df


def fake_field_proposal(**kw):
    """FieldProposal ORM mock."""
    p = MagicMock()
    p.id = kw.get("id", 1)
    p.job_id = kw.get("job_id", 1)
    p.document_field_id = kw.get("document_field_id", 1)
    p.step = kw.get("step", "VALIDATION")
    p.value = kw.get("value", "Martin")
    p.value_type = kw.get("value_type", "TEXT")
    p.reason = kw.get("reason", None)
    return p


def fake_job(**kw):
    """Job ORM mock."""
    j = MagicMock()
    j.id = kw.get("id", 1)
    j.dataset_id = kw.get("dataset_id", 1)
    j.document_id = kw.get("document_id", 1)
    j.agent_id = kw.get("agent_id", 42)
    j.state = kw.get("state", "ASSIGNED")
    j.step = kw.get("step", "VALIDATION")
    j.started_at = kw.get("started_at", NOW)
    j.submitted_at = kw.get("submitted_at", None)
    j.document = kw.get("document", fake_doc())
    j.field_proposals = kw.get("field_proposals", [])
    return j


def fake_user(**kw):
    """User ORM mock."""
    u = MagicMock()
    u.id = kw.get("id", 42)
    u.email = kw.get("email", "agent@example.com")
    return u


# ---------------------------------------------------------------------------
# Fixtures pytest
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """AsyncSession entièrement mocké.

    db.add() est synchrone — on le remplace par un MagicMock standard pour
    éviter les warnings de coroutine non awaitée.
    """
    db = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def client(mock_db):
    """TestClient FastAPI avec la dépendance get_db remplacée par mock_db."""

    async def override():
        yield mock_db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
