"""
 scripts/seed.py
 ----------
 Seed unifie de la base ADAM.
 Deux modes :
     - Sans JSON : donnees de test formulaire demo hardcodees
     - Avec JSON : schema et champs derives d'un fichier format formulaire v0.3
Usage :
    python scripts/seed.py
    python scripts/seed.py --reset
    python scripts/seed.py --json form_demo_v0.3.json
    python scripts/seed.py --json form_demo_v0.3.json --reset
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from adam_core.core.config import CoreSettings
from adam_core.utils.hashing import sha256_bytes
from adam_core.db.session import create_tables, get_engine, init_engine
from adam_core.enums.ocr import OcrProvider, StorageMode
from adam_core.enums.roles import UserRole
from adam_core.enums.status import (
    DatasetStatus,
    DocumentFieldStatus,
    DocumentStatus,
    FieldValueType,
    ProjectStatus,
    UserStatus,
)
from adam_core.models import (
    Dataset,
    DocSchema,
    Document,
    DocumentField,
    FieldSpec,
    File,
    OcrResult,
    Organisation,
    Project,
    User,
    UserProject,
)
settings = CoreSettings()
SEPARATOR = "-" * 55
# Reset
async def reset_db(session: AsyncSession) -> None:
    print(" Reset de la base...")
    tables = [
        "document_field", "ocr_result", "document", "file",
        "dataset", "field_spec", "doc_schema",
        "user_project", "project", "user", "organisation",
    ]
    for table in tables:
        await session.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))
    await session.commit()
    print(" Tables videes")
# Infrastructure commune
async def seed_infrastructure(session: AsyncSession) -> Tuple:
    print("\n [1/3] Organisations...")
    org_alpha = Organisation(name="Org Alpha", slug="org-alpha")
    org_beta = Organisation(name="Org Beta", slug="org-beta")
    session.add_all([org_alpha, org_beta])
    await session.flush()
    print(f"        {org_alpha}")
    print(f"        {org_beta}")
    print(" [2/3] Users...")
    admin = User(
        organisation_id=org-beta.id,
        email="admin@example.com",
        full_name="Admin Demo",
        matricule="MAT00001",
        status=UserStatus.ACTIVE.value,
    )
    operator = User(
        organisation_id=org-beta.id,
        email="operateur@example.com",
       full_name="Operateur Demo",
       matricule="MAT00002",
       status=UserStatus.ACTIVE.value,
    )
    session.add_all([admin, operator])
    await session.flush()
    print(f"        {admin}")
    print(f"        {operator}")
    print(" [3/3] Project + UserProjects...")
    project = Project(
       organisation_id=org-beta.id,
       name="Projet Demo Formulaires",
       description="Labellisation de formulaires administratifs demo",
       status=ProjectStatus.ACTIVE.value,
    )
    session.add(project)
    await session.flush()
    session.add_all([
       UserProject(user_id=admin.id, project_id=project.id, role=UserRole.ADMIN.value),
       UserProject(user_id=operator.id, project_id=project.id, role=UserRole.OPERATOR.value),
    ])
    await session.flush()
    print(f"        {project}")
    return org_beta, admin, operator, project
# Mode 1 : Donnees hardcodees
HARDCODED_FIELD_SPECS = [
    ("demandeur", "Demandeur", "demandeur.nom", "Nom de naissance", FieldValueType.TEXT.value, 1),
    ("demandeur", "Demandeur", "demandeur.prenom", "Prenom", FieldValueType.TEXT.value, 1),
    ("demandeur", "Demandeur", "demandeur.date_naissance", "Date de naissance", FieldValueType.DATE.value, 1),
    ("demandeur", "Demandeur", "demandeur.civilite_m", "Monsieur", FieldValueType.BOOLEAN.value, 1),
    ("demandeur", "Demandeur", "demandeur.civilite_mme", "Madame", FieldValueType.BOOLEAN.value, 1),
    ("bien", "Bien", "bien.adresse", "Adresse du bien", FieldValueType.TEXT.value, 1),
    ("bien", "Bien", "bien.valeur", "Valeur du bien (EUR)", FieldValueType.NUMBER.value, 1),
    ("bien", "Bien", "bien.superficie", "Superficie (m2)", FieldValueType.NUMBER.value, 1),
    ("creance", "Creance", "creance.montant", "Montant creance", FieldValueType.NUMBER.value, 1),
    ("creance", "Creance", "creance.date_echeance", "Date d'echeance", FieldValueType.DATE.value, 1),
]
HARDCODED_OCR_VALUES: Dict = {
    "demandeur.nom":                 ("NOM01",                      0.98, [182,282,298,182,298,168,82,168]),
    "demandeur.prenom":              ("P02",                        0.97, [82,142,288,142,288,168,82,168]),
    "demandeur.date_naissance":      ("1985-01-01",                  0.95, [82,182,218,182,218,208,82,208]),
    "demandeur.civilite_m":          ("true",                        1.00, [82,222,118,222,118,238,82,238]),
    "demandeur.civilite_mme":        ("false",                       1.00, [132,222,178,222,178,238,132,238]),
    "bien.adresse":                 ("1 rue Demo 00000 Villedemo", 0.91, [82,102,498,102,498,128,82,128]),
    "bien.valeur":                  ("450000",                      0.88, [82,142,298,142,298,168,82,168]),
    "bien.superficie":              ("85",                          0.93, [322,142,448,142,448,168,322,168]),
    "creance.montant":              ("320000",                      0.90, [82,222,298,222,298,248,82,248]),
    "creance.date_echeance":        ("2040-01-15",                  0.94, [322,222,498,222,498,248,322,248]),
}
HARDCODED_RAW_JSON = {
    "format_version": "0.3",
    "document_id": "form_demo_001",
    "coordinate_unit": "pixel",
    "page_count": 2,
    "metadata": {"ocr": {"provider": "PULSAR", "processed_at": "2024-01-15T10:00:00Z"}},
    "pages": [],
}
async def seed_hardcoded(session: AsyncSession, project: Project) -> None:
    print("\n --- Mode : donnees hardcodees (Formulaire Demo v2) ---")
    print(" [4/8] DocSchema...")
    schema = DocSchema(
       project_id=project.id,
       version=2,
       name="Schema Formulaire Demo v2",
       document_type="FORM_DEMO_02",
    )
    session.add(schema)
    await session.flush()
    print(f"        {schema}")
    print(" [5/8] FieldSpecs...")
    field_specs = []
    for i, (sec_id, sec_label, key, label, ftype, page) in enumerate(HARDCODED_FIELD_SPECS):
       fs = FieldSpec(
           schema_id=schema.id, page=page,
           section_id=sec_id, section_label=sec_label,
           field_key=key, display_label=label,
           value_type=ftype, required=False,
           display_order=i,
       )
       field_specs.append(fs)
    session.add_all(field_specs)
    await session.flush()
    print(f"    --- {len(field_specs)} FieldSpecs crees")
    await _seed_dataset_to_fields(
       session, project, schema, field_specs,
       file_path="/pvc/org-beta/forms/2024_01/2024_01_15_1200/form_demo_001.pdf",
       file_name="form_demo_001.pdf",
       raw_json=HARDCODED_RAW_JSON,
       ocr_values=HARDCODED_OCR_VALUES,
       document_id_str="form_demo_001",
       step_offset=6,
    )
# Mode 2 : Depuis JSON formulaire
async def seed_from_form_json(
    session: AsyncSession, project: Project, json_path: Path
) -> None:
    from adam_core.schemas.interface_contract import SmartdocDocument
    print(f"\n --- Mode : FORM JSON ({json_path.name}) ---")
    with open(json_path, encoding="utf-8") as f:
       json_raw = json.load(f)
    form_doc = SmartdocDocument.model_validate(json_raw)
    print(f" JSON valide : {form_doc.page_count} pages, document_id={form_doc.document_id}")
    print(" [4/8] DocSchema...")
    schema = DocSchema(
       project_id=project.id,
       version=1,
       name="Formulaire Demo",
       document_type="FORM_DEMO_01",
    )
    session.add(schema)
    await session.flush()
    print(f"        {schema}")
    print(" [5/8] FieldSpecs (dérivés du JSON)...")
    specs_data = form_doc.extract_field_specs()
    field_spec_index: Dict = {}
    field_specs = []
    for spec in specs_data:
       fs = FieldSpec(
           schema_id=schema.id,
           page=spec["page"],
           section_id=spec["section_id"],
           section_label=spec["section_label"],
           field_key=spec["field_key"],
           display_label=spec["display_label"],
           value_type=spec["value_type"],
           required=spec["required"],
           display_order=spec["display_order"],
           polygon=spec["polygon"],
       )
       field_specs.append(fs)
       session.add(fs)
       await session.flush()
       field_spec_index[(spec["section_id"], spec["field_key"])] = fs
    print(f"        {len(field_specs)} FieldSpecs créés depuis {form_doc.page_count} pages")
    print(" [6/8] Dataset...")
    dataset = Dataset(
       project_id=project.id, schema_id=schema.id,
       name="Lot Formulaires Demo - Seed",
       ocr_provider=OcrProvider.PULSAR.value,
       status=DatasetStatus.ACTIVE.value,
       required_operators=2,
       configs={"confidence_threshold": 0.8},
    )
    session.add(dataset)
    await session.flush()
    print(f"        {dataset=}")
    print(" [7/8] File + Document...")
    json_bytes = json.dumps(json_raw, ensure_ascii=False).encode("utf-8")
    sha256 = sha256_bytes(json_bytes)
    file_ = File(
       file_path=f"/pvc/forms/demo/{form_doc.document_id}.pdf",
       storage_type="pvc", mime_type="application/pdf",
       page_count=form_doc.page_count,
       file_size_bytes=len(json_bytes),
       sha256_checksum=sha256,
    )
    session.add(file_)
    await session.flush()
    document = Document(
       dataset_id=dataset.id, file_id=file_.id,
       file_name=f"{form_doc.document_id}.pdf",
       metadata={
           "format_version": form_doc.format_version,
           "document_id": form_doc.document_id,
           "coordinate_unit": form_doc.coordinate_unit,
       },
       status=DocumentStatus.IN_PROGRESS.value,
    )
    session.add(document)
    await session.flush()
    print(f"        {file_}")
    print(f"        {document}")
    print("    [8/8] OcrResult + DocumentFields...")
    ocr_result = OcrResult(
       document_id=document.id, dataset_id=dataset.id,
       storage_mode=StorageMode.JSONB.value,
       raw_json=json_raw,
    )
    session.add(ocr_result)
    await session.flush()
    doc_fields = []
    skipped = 0
    for _, section, kv in form_doc.iter_kv_pairs():
       fs = field_spec_index.get((section.id, kv.field_key))
       if not fs:
           skipped += 1
           continue
       doc_fields.append(DocumentField(
           document_id=document.id, field_spec_id=fs.id,
           group_id=kv.group_id,
           ocr_value=kv.extracted_value, resolved_value=kv.extracted_value,
           status=DocumentFieldStatus.PENDING.value,
           ocr_confidence=kv.confidence, consensus_reached=False,
           ocr_polygon=kv.polygon,
       ))
    session.add_all(doc_fields)
    await session.flush()
    print(f"            {len(doc_fields)} DocumentFields crees")
    if skipped:
       print(f"            {skipped} KVPairs ignores (fieldSpec manquant)")
    print(f"\n Resume : {len(field_specs)} FieldSpecs, {len(doc_fields)} DocumentFields, {form_doc.page_count}")
# Helper partagé
async def _seed_dataset_to_fields(
    session: AsyncSession,
    project: Project,
    schema: DocSchema,
    field_specs: List[FieldSpec],
    file_path: str,
    file_name: str,
    raw_json: dict,
    ocr_values: Dict,
    document_id_str: str,
    step_offset: int,
) -> None:
    print(f"  [{step_offset}/8] Dataset...")
    dataset = Dataset(
       project_id=project.id, schema_id=schema.id,
       name="Lot janvier 2024",
       description="Premier lot de documents",
       ocr_provider=OcrProvider.PULSAR.value,
       status=DatasetStatus.ACTIVE.value,
       required_operators=2,
       configs={"confidence_threshold": 0.8, "export_format": "json_pdf"},
    )
    session.add(dataset)
    await session.flush()
    print(f"        {dataset}")
    print(f"  [{step_offset + 1}/8] File + Document...")
    json_bytes = json.dumps(raw_json, ensure_ascii=False).encode("utf-8")
    sha256 = sha256_bytes(json_bytes)
    file_ = File(
       file_path=file_path, storage_type="PVC",
       mime_type="application/pdf", page_count=raw_json.get("page_count", 2),
       file_size_bytes=len(json_bytes), sha256_checksum=sha256,
    )
    session.add(file_)
    await session.flush()
    document = Document(
       dataset_id=dataset.id, file_id=file_.id, file_name=file_name,
       metadata={"source": "PVC", "lot": "2024-01", "reception_date": "2024-01-15"},
       status=DocumentStatus.IN_PROGRESS.value,
    )
    session.add(document)
    await session.flush()
    print(f"        {file_}")
    print(f"        {document}")
    print(f"  [{step_offset + 2}/8] OcrResult + DocumentFields...")
    ocr_result = OcrResult(
       document_id=document.id, dataset_id=dataset.id,
       storage_mode=StorageMode.JSONB.value, raw_json=raw_json,
    )
    session.add(ocr_result)
    await session.flush()
    doc_fields = []
    for fs in field_specs:
       ocr_val, confidence, polygon = ocr_values.get(fs.field_key, (None, None, None))
       doc_fields.append(DocumentField(
           document_id=document.id, field_spec_id=fs.id, group_id=None,
           ocr_value=ocr_val, resolved_value=ocr_val,
           status=DocumentFieldStatus.PENDING.value,
           ocr_confidence=confidence, consensus_reached=False, ocr_polygon=polygon,
       ))
    session.add_all(doc_fields)
    await session.flush()
    print(f"        {len(doc_fields)} DocumentFields crees")
# Main
async def main(reset: bool, json_path: Optional[Path]) -> None:
    init_engine(settings.async_database_url, echo=False)
    await create_tables()
    factory = async_sessionmaker(bind=get_engine(), expire_on_commit=False)
    async with factory() as session:
       if reset:
           await reset_db(session)
       _, admin, operator, project = await seed_infrastructure(session)
       if json_path:
           await seed_from_form_json(session, project, json_path)
       else:
           await seed_hardcoded(session, project)
       await session.commit()
    await get_engine().dispose()
    print("\n Seed termine avec succes")
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed ADAM database")
    parser.add_argument("--reset", action="store_true", help="Vide les tables avant de seeder")
    parser.add_argument("--json", default=None, help="Chemin vers un fichier JSON format formulaire v0.3")
    args = parser.parse_args()
    json_path = None
    if args.json:
       json_path = Path(args.json)
       if not json_path.exists():
           json_path = Path(__file__).parent.parent / args.json
       if not json_path.exists():
           json_path = Path(__file__).parent / args.json
       if not json_path.exists():
           print(f"Fichier introuvable : {args.json}")
           sys.exit(1)
    print(SEPARATOR)
    print("Seed de la base de donnees")
    print(f" Mode : {'FORM JSON' if json_path else 'Donnees hardcodees'}")
    print(SEPARATOR)
    asyncio.run(main(reset=args.reset, json_path=json_path))
    print(SEPARATOR)
