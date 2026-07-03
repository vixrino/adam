"""Tests unitaires des schémas Pydantic — aucune base de données requise."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from adam_core.schemas.responses import (
    DatasetOut,
    DatasetStatsOut,
    DocumentFieldInPageOut,
    DocumentFieldOut,
    DocumentFieldPatchOut,
    DocumentFieldsBySectionOut,
    DocumentFullOut,
    DocumentJobOut,
    DocumentOcrResultOut,
    DocumentOut,
    DocumentPageOut,
    DocumentSectionOut,
    FieldBySectionItemOut,
    FieldProposalOut,
    FileCreatedOut,
    FileDetailOut,
    FileIngestionItemOut,
    FileOut,
    FilePatchOut,
    FileRefOut,
    IngestionOut,
    JobCreatedOut,
    JobDetailOut,
    JobFieldItemOut,
    JobOut,
    JobPageOut,
    JobSectionOut,
    JobSubmitOut,
    OrganisationOut,
)

NOW = datetime(2026, 6, 26, 12, 0, 0, tzinfo=timezone.utc)
CHECKSUM = "a" * 64


# ---------------------------------------------------------------------------
# OrganisationOut
# ---------------------------------------------------------------------------


class TestOrganisationOut:
    def test_valid(self):
        o = OrganisationOut(id=1, name="Org Centrale", slug="org-centrale")
        assert o.id == 1
        assert o.slug == "org-centrale"

    def test_from_orm(self):
        class FakeOrg:
            id = 3
            name = "BDF"
            slug = "bdf"

        o = OrganisationOut.model_validate(FakeOrg())
        assert o.id == 3


# ---------------------------------------------------------------------------
# DatasetOut / DatasetStatsOut
# ---------------------------------------------------------------------------


class TestDatasetOut:
    def test_description_optional(self):
        d = DatasetOut(
            id=1,
            project_id=2,
            schema_id=3,
            name="DS",
            status="ACTIVE",
            ocr_provider="PULSAR",
            required_operators=3,
            ocr_job_enabled=True,
        )
        assert d.description is None

    def test_with_description(self):
        d = DatasetOut(
            id=1,
            project_id=2,
            schema_id=3,
            name="DS",
            description="Lot de test",
            status="ACTIVE",
            ocr_provider="PULSAR",
            required_operators=3,
            ocr_job_enabled=True,
        )
        assert d.description == "Lot de test"

    def test_from_orm(self):
        class FakeDataset:
            id = 9
            project_id = 1
            schema_id = 2
            name = "Mon DS"
            description = None
            status = "DRAFT"
            ocr_provider = "GOOGLE"
            required_operators = 2
            ocr_job_enabled = False

        d = DatasetOut.model_validate(FakeDataset())
        assert d.id == 9
        assert d.ocr_job_enabled is False


class TestDatasetStatsOut:
    def test_valid(self):
        s = DatasetStatsOut(dataset_id=1, documents_total=50, documents_validated=12)
        assert s.documents_total == 50
        assert s.documents_validated == 12


# ---------------------------------------------------------------------------
# FileOut / FileDetailOut / FileCreatedOut / FilePatchOut / FileRefOut
# ---------------------------------------------------------------------------


class TestFileOut:
    def test_valid(self):
        f = FileOut(
            id=1,
            file_path="/pvc/a.pdf",
            sha256_checksum=CHECKSUM,
            file_size_bytes=1024,
            page_count=5,
            mime_type="application/pdf",
            storage_type="pvc",
            created_at=NOW,
        )
        assert f.page_count == 5
        assert f.storage_type == "pvc"

    def test_from_orm(self):
        class FakeFile:
            id = 7
            file_path = "/pvc/b.pdf"
            sha256_checksum = CHECKSUM
            file_size_bytes = 512
            page_count = 2
            mime_type = "application/pdf"
            storage_type = "s3"
            created_at = NOW

        f = FileOut.model_validate(FakeFile())
        assert f.id == 7
        assert f.storage_type == "s3"


class TestFileDetailOut:
    def test_includes_documents_count(self):
        f = FileDetailOut(
            id=1,
            file_path="/pvc/a.pdf",
            sha256_checksum=CHECKSUM,
            file_size_bytes=100,
            page_count=1,
            mime_type="application/pdf",
            storage_type="pvc",
            created_at=NOW,
            documents_count=5,
        )
        assert f.documents_count == 5

    def test_zero_documents(self):
        f = FileDetailOut(
            id=2,
            file_path="/pvc/b.pdf",
            sha256_checksum=CHECKSUM,
            file_size_bytes=200,
            page_count=3,
            mime_type="application/pdf",
            storage_type="pvc",
            created_at=NOW,
            documents_count=0,
        )
        assert f.documents_count == 0


class TestFileCreatedOut:
    def test_not_deduplicated(self):
        f = FileCreatedOut(id=1, file_path="/p", sha256_checksum=CHECKSUM, deduplicated=False)
        assert f.deduplicated is False

    def test_deduplicated(self):
        f = FileCreatedOut(id=2, file_path="/p", sha256_checksum=CHECKSUM, deduplicated=True)
        assert f.deduplicated is True


class TestFilePatchOut:
    def test_valid(self):
        f = FilePatchOut(id=1, file_path="/pvc/new.pdf", page_count=10)
        assert f.file_path == "/pvc/new.pdf"
        assert f.page_count == 10


class TestFileRefOut:
    def test_valid(self):
        f = FileRefOut(id=1, path="/pvc/test.pdf")
        assert f.path == "/pvc/test.pdf"


# ---------------------------------------------------------------------------
# DocumentOut / DocumentFullOut et schémas imbriqués
# ---------------------------------------------------------------------------


class TestDocumentOut:
    def test_defaults(self):
        d = DocumentOut(
            id=1,
            dataset_id=1,
            file_id=1,
            file_name="doc.pdf",
            status="RECEIVED",
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert d.page_count is None
        assert d.image_paths is None
        assert d.metadata is None

    def test_with_page_count(self):
        d = DocumentOut(
            id=1,
            dataset_id=1,
            file_id=1,
            file_name="doc.pdf",
            status="RECEIVED",
            page_count=7,
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert d.page_count == 7

    def test_metadata_alias(self):
        """DocumentOut lit metadata via l'alias validation_alias='metadata_'."""

        class FakeDoc:
            id = 1
            dataset_id = 1
            file_id = 1
            file_name = "x.pdf"
            status = "RECEIVED"
            metadata_ = {"source": "scan"}
            image_paths = None
            page_count = 3
            updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

        d = DocumentOut.model_validate(FakeDoc())
        assert d.metadata == {"source": "scan"}


class TestDocumentFieldInPageOut:
    def test_optional_fields(self):
        f = DocumentFieldInPageOut(id=1, status="PENDING")
        assert f.field_key is None
        assert f.ocr_value is None
        assert f.resolved_value is None

    def test_full(self):
        f = DocumentFieldInPageOut(
            id=5,
            field_key="nom",
            ocr_value="Martin",
            resolved_value="MARTIN",
            status="CORRECTED",
        )
        assert f.resolved_value == "MARTIN"


class TestDocumentSectionOut:
    def test_empty_fields(self):
        s = DocumentSectionOut(id="section_1")
        assert s.fields == []

    def test_with_fields(self):
        field = DocumentFieldInPageOut(id=1, status="PENDING")
        s = DocumentSectionOut(id="s1", fields=[field])
        assert len(s.fields) == 1


class TestDocumentPageOut:
    def test_empty_sections(self):
        p = DocumentPageOut(page_number=1)
        assert p.sections == []

    def test_with_sections(self):
        section = DocumentSectionOut(id="s1")
        p = DocumentPageOut(page_number=2, sections=[section])
        assert p.page_number == 2
        assert len(p.sections) == 1


class TestDocumentFullOut:
    def test_minimal(self):
        d = DocumentFullOut(id=1, file_name="x.pdf", status="RECEIVED")
        assert d.pages == []
        assert d.ocr_results == []
        assert d.jobs == []
        assert d.file is None

    def test_with_nested_pages(self):
        field = DocumentFieldInPageOut(id=1, status="PENDING")
        section = DocumentSectionOut(id="s1", fields=[field])
        page = DocumentPageOut(page_number=1, sections=[section])
        d = DocumentFullOut(id=1, file_name="x.pdf", status="RECEIVED", pages=[page])
        assert len(d.pages[0].sections[0].fields) == 1

    def test_with_jobs_and_ocr(self):
        job = DocumentJobOut(id=10, state="SUBMITTED")
        ocr = DocumentOcrResultOut(id=5)
        d = DocumentFullOut(
            id=1, file_name="x.pdf", status="RECEIVED", jobs=[job], ocr_results=[ocr]
        )
        assert d.jobs[0].state == "SUBMITTED"
        assert d.ocr_results[0].id == 5


# ---------------------------------------------------------------------------
# DocumentField by-section
# ---------------------------------------------------------------------------


class TestFieldBySectionItemOut:
    def test_key_optional(self):
        f = FieldBySectionItemOut(id=1)
        assert f.field_key is None

    def test_with_key(self):
        f = FieldBySectionItemOut(id=1, field_key="date_naissance")
        assert f.field_key == "date_naissance"


class TestDocumentFieldsBySectionOut:
    def test_valid(self):
        item = FieldBySectionItemOut(id=1, field_key="nom")
        d = DocumentFieldsBySectionOut(document_id=5, sections={"s1": [item]})
        assert d.document_id == 5
        assert len(d.sections["s1"]) == 1

    def test_empty_sections(self):
        d = DocumentFieldsBySectionOut(document_id=1, sections={})
        assert d.sections == {}


# ---------------------------------------------------------------------------
# DocumentFieldOut / DocumentFieldPatchOut
# ---------------------------------------------------------------------------


class TestDocumentFieldOut:
    def test_defaults(self):
        f = DocumentFieldOut(
            id=1, document_id=1, field_spec_id=1, status="PENDING", consensus_reached=False
        )
        assert f.ocr_polygon is None
        assert f.resolved_value is None
        assert f.group_id is None

    def test_with_polygon(self):
        f = DocumentFieldOut(
            id=1,
            document_id=1,
            field_spec_id=1,
            status="CORRECTED",
            consensus_reached=True,
            ocr_polygon=[0.1, 0.2, 0.8, 0.9],
        )
        assert len(f.ocr_polygon) == 4

    def test_from_orm(self):
        class FakeField:
            id = 7
            document_id = 2
            field_spec_id = 3
            group_id = None
            ocr_value = "Martin"
            resolved_value = None
            status = "PENDING"
            ocr_confidence = 0.95
            consensus_reached = False
            ocr_polygon = None

        f = DocumentFieldOut.model_validate(FakeField())
        assert f.ocr_confidence == 0.95


class TestDocumentFieldPatchOut:
    def test_valid(self):
        p = DocumentFieldPatchOut(id=1, status="CORRECTED", resolved_value="OK")
        assert p.resolved_value == "OK"

    def test_no_value(self):
        p = DocumentFieldPatchOut(id=2, status="PENDING")
        assert p.resolved_value is None


# ---------------------------------------------------------------------------
# Job schemas
# ---------------------------------------------------------------------------


class TestJobOut:
    def test_submitted_at_optional(self):
        j = JobOut(
            id=1,
            dataset_id=1,
            document_id=1,
            agent_id=5,
            state="ASSIGNED",
            step="VALIDATION",
            started_at=NOW,
        )
        assert j.submitted_at is None

    def test_with_submitted_at(self):
        j = JobOut(
            id=1,
            dataset_id=1,
            document_id=1,
            agent_id=5,
            state="SUBMITTED",
            step="VALIDATION",
            started_at=NOW,
            submitted_at=NOW,
        )
        assert j.submitted_at == NOW


class TestJobDetailOut:
    def test_empty_pages(self):
        j = JobDetailOut(
            id=1,
            step="VALIDATION",
            state="ASSIGNED",
            agent_id=1,
            document_id=1,
            dataset_id=1,
            started_at=NOW,
        )
        assert j.pages == []

    def test_with_pages(self):
        field = JobFieldItemOut(id=1, step="VALIDATION")
        section = JobSectionOut(section_id="s1", fields=[field])
        page = JobPageOut(page=1, sections=[section])
        j = JobDetailOut(
            id=1,
            step="VALIDATION",
            state="IN_PROGRESS",
            agent_id=1,
            document_id=1,
            dataset_id=1,
            started_at=NOW,
            pages=[page],
        )
        assert j.pages[0].sections[0].fields[0].id == 1


class TestFieldProposalOut:
    def test_optional_value(self):
        p = FieldProposalOut(id=1, job_id=1, document_field_id=1, step="VALIDATION")
        assert p.value is None
        assert p.value_type is None

    def test_with_value(self):
        p = FieldProposalOut(
            id=2, job_id=1, document_field_id=3, step="CONSENSUS", value="Dupont", value_type="TEXT"
        )
        assert p.value == "Dupont"


# ---------------------------------------------------------------------------
# Ingestion schemas
# ---------------------------------------------------------------------------


class TestFileIngestionItemOut:
    def test_created(self):
        item = FileIngestionItemOut(
            file_name="doc.pdf", status="created", document_id=1, file_id=2, file_reused=False
        )
        assert item.status == "created"
        assert item.file_reused is False

    def test_rejected(self):
        item = FileIngestionItemOut(file_name="bad.txt", status="rejected", reason="non-PDF")
        assert item.reason == "non-PDF"
        assert item.document_id is None

    def test_already_exists(self):
        item = FileIngestionItemOut(
            file_name="dup.pdf", status="already_exists", file_id=5, file_reused=True
        )
        assert item.file_reused is True


class TestIngestionOut:
    def test_counts(self):
        items = [
            FileIngestionItemOut(file_name="a.pdf", status="created", document_id=1, file_id=1),
            FileIngestionItemOut(file_name="b.pdf", status="rejected", reason="non-PDF"),
            FileIngestionItemOut(
                file_name="c.pdf", status="already_exists", file_id=2, file_reused=True
            ),
        ]
        o = IngestionOut(
            dataset_id=1, received=3, created=1, already_exists=1, rejected=1, results=items
        )
        assert o.received == 3
        assert o.created == 1
        assert o.rejected == 1
        assert len(o.results) == 3
