"""
scripts/seed.py
----------------

Seed unifie de la base NOTA.

Deux modes :
  - Sans JSON : donnees de test CERFA 13594 hardcodees
  - Avec JSON : schema et champs derives d'un fichier SMARTDOC v0.3

Usage :
    python scripts/seed.py
    python scripts/seed.py --reset
    python scripts/seed.py --json cerfa_example_v0_3.json
    python scripts/seed.py --json cerfa_example_v0_3.json --reset
"""

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nota_core.core.config import CoreSettings
from nota_core.db.session import create_tables, get_engine, init_engine
from nota_core.enums.ocr import OcrProvider, StorageMode
from nota_core.enums.roles import PlatformRole, ProjectRole
from nota_core.enums.status import (
    DatasetStatus,
    DocumentFieldStatus,
    DocumentStatus,
    FieldValueType,
    ProjectStatus,
    UserStatus,
)
from nota_core.models import (
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

SEPARATOR = "=" * 55


# Reset


async def reset_db(session: AsyncSession) -> None:
    print("  Reset de la base...")
    tables = [
        "document_field", "ocr_result", "document", "file",
        "dataset", "field_spec", "doc_schema",
        "user_project", "project", "user", "organisation",
    ]
    for table in tables:
        await session.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))
    await session.commit()
    print("  Tables videes")


# Infrastructure commune

#: (slug, nom). Une organisation par direction.
ORGANISATIONS = [
    ("dgrh", "DGRH"),
    ("dires", "DIRES"),
]

#: Agents par slug d'organisation :
#: (matricule, prenom, nom, role projet, role plateforme).
#:
#: Identites fictives. Les matricules V654846, I659418 et MAT00003 gardent en
#: revanche leur signification : le mock FBI, check_project_scoping.py et la
#: valeur par defaut d'API_DEV_MATRICULE s'appuient dessus.
AGENTS = {
    "dgrh": [
        ("V654846", "Philippe", "Bernard", ProjectRole.BUSINESS_ADMIN, None),
        ("I659418", "Nadia", "Fontaine", ProjectRole.OPERATOR, None),
        ("MAT00003", "Sylvie", "Marchand", None, PlatformRole.NOTA_ADMIN),
        ("K318204", "Karim", "Belkacem", ProjectRole.OPERATOR, None),
    ],
    "dires": [
        ("M472915", "Martine", "Vasseur", ProjectRole.BUSINESS_ADMIN, None),
        ("T205663", "Thomas", "Roux", ProjectRole.OPERATOR, None),
        ("A889341", "Awa", "Diallo", ProjectRole.OPERATOR, None),
    ],
}

#: Projet type, decline a l'identique dans chaque organisation. Deux projets
#: homonymes ne se confondent pas : le filtrage par organisation les separe.
PROJECT_NAME = "SUREN Cerfa"
PROJECT_DESCRIPTION = "Labellisation des CERFA de surendettement"

#: Nom des lots : le formulaire et sa version.
CERFA_DATASET_NAME = "cerfa_13594-02_v2"


def _email(first_name: str, last_name: str) -> str:
    return f"{first_name.lower()}.{last_name.lower()}@bdf.fr"


async def seed_infrastructure(session: AsyncSession) -> Tuple:
    print("\n [1/3] Organisations...")
    organisations = {}
    for slug, name in ORGANISATIONS:
        org = Organisation(name=name, slug=slug)
        session.add(org)
        organisations[slug] = org
    await session.flush()
    for org in organisations.values():
        print(f"       {org}")

    print(" [2/3] Users...")
    users_by_slug: Dict[str, List[Tuple[User, Optional[ProjectRole]]]] = {}
    for slug, agents in AGENTS.items():
        users_by_slug[slug] = []
        for matricule, first_name, last_name, project_role, platform_role in agents:
            user = User(
                organisation_id=organisations[slug].id,
                email=_email(first_name, last_name),
                full_name=f"{first_name} {last_name}",
                matricule=matricule,
                platform_role=platform_role.value if platform_role else None,
                status=UserStatus.ACTIVE.value,
            )
            session.add(user)
            users_by_slug[slug].append((user, project_role))
    await session.flush()
    for slug, entries in users_by_slug.items():
        for user, project_role in entries:
            role = user.platform_role or (project_role.value if project_role else "sans role")
            print(f"       [{slug}] {user.matricule} {user.full_name} - {role}")

    print(" [3/3] Projects + UserProjects...")
    projects = {}
    for slug, org in organisations.items():
        project = Project(
            organisation_id=org.id,
            name=PROJECT_NAME,
            description=PROJECT_DESCRIPTION,
            status=ProjectStatus.ACTIVE.value,
        )
        session.add(project)
        projects[slug] = project
    await session.flush()

    for slug, entries in users_by_slug.items():
        for user, project_role in entries:
            # L'administrateur NOTA n'adhere a aucun projet : son role de
            # plateforme neutralise deja le filtrage.
            if project_role is None:
                continue
            session.add(
                UserProject(
                    user_id=user.id,
                    project_id=projects[slug].id,
                    role=project_role.value,
                )
            )
    await session.flush()
    for project in projects.values():
        print(f"       {project}")

    users = {user.matricule: user for user, _ in users_by_slug["dgrh"]}
    return organisations["dires"], users["V654846"], users["I659418"], projects["dgrh"]


# Mode 1 : Donnees hardcodees


HARDCODED_FIELD_SPECS = [
    ("deposant", "Deposant", "deposant.nom",            "Nom de naissance",     FieldValueType.TEXT.value,    1, True,  [80, 100, 300, 100, 300, 130, 80, 130]),
    ("deposant", "Deposant", "deposant.prenom",         "Prenom",               FieldValueType.TEXT.value,    1, True,  [80, 140, 300, 140, 300, 170, 80, 170]),
    ("deposant", "Deposant", "deposant.date_naissance", "Date de naissance",    FieldValueType.DATE.value,    1, True,  [80, 180, 220, 180, 220, 210, 80, 210]),
    ("deposant", "Deposant", "deposant.civilite_m",     "Monsieur",             FieldValueType.BOOLEAN.value, 1, False, [80, 220, 120, 220, 120, 240, 80, 240]),
    ("deposant", "Deposant", "deposant.civilite_mme",   "Madame",               FieldValueType.BOOLEAN.value, 1, False, [130, 220, 180, 220, 180, 240, 130, 240]),
    ("bien",     "Bien",     "bien.adresse",            "Adresse du bien",      FieldValueType.TEXT.value,    2, True,  [80, 100, 500, 100, 500, 130, 80, 130]),
    ("bien",     "Bien",     "bien.valeur",             "Valeur du bien (EUR)", FieldValueType.NUMBER.value,  2, True,  [80, 140, 300, 140, 300, 170, 80, 170]),
    ("bien",     "Bien",     "bien.superficie",         "Superficie (m2)",      FieldValueType.NUMBER.value,  2, False, [320, 140, 450, 140, 450, 170, 320, 170]),
    ("creance",  "Creance",  "creance.montant",         "Montant creance",      FieldValueType.NUMBER.value,  2, True,  [80, 220, 300, 220, 300, 250, 80, 250]),
    ("creance",  "Creance",  "creance.date_echeance",   "Date d echeance",      FieldValueType.DATE.value,    2, True,  [320, 220, 500, 220, 500, 250, 320, 250]),
]

HARDCODED_OCR_VALUES: Dict = {
    "deposant.nom":            ("MOULIN",                     0.98, [82, 102, 298, 102, 298, 128, 82, 128]),
    "deposant.prenom":         ("Jean",                       0.97, [82, 142, 200, 142, 200, 168, 82, 168]),
    "deposant.date_naissance": ("1980-01-06",                 0.95, [82, 182, 218, 182, 218, 208, 82, 208]),
    "deposant.civilite_m":     ("true",                       1.00, [82, 222, 118, 222, 118, 238, 82, 238]),
    "deposant.civilite_mme":   ("false",                      1.00, [132, 222, 178, 222, 178, 238, 132, 238]),
    "bien.adresse":            ("115 rue Reaumur 75002 Paris", 0.91, [82, 102, 498, 102, 498, 128, 82, 128]),
    "bien.valeur":             ("450000",                     0.88, [82, 142, 298, 142, 298, 168, 82, 168]),
    "bien.superficie":         ("85",                         0.93, [322, 142, 448, 142, 448, 168, 322, 168]),
    "creance.montant":         ("320000",                     0.90, [82, 222, 298, 222, 298, 248, 82, 248]),
    "creance.date_echeance":   ("2046-01-15",                 0.94, [322, 222, 498, 222, 498, 248, 322, 248]),
}

HARDCODED_RAW_JSON = {
    "smartdoc_version": "0.3",
    "document_id": "cerfa_13594_sample",
    "coordinate_unit": "pixel",
    "page_count": 2,
    "metadata": {"ocr": {"provider": "PULSAR", "processed_at": "2026-01-15T10:00:00Z"}},
    "pages": [],
}


async def seed_hardcoded(session: AsyncSession, project: Project) -> None:
    print("\n --- Mode : donnees hardcodees (CERFA 13594 v2) ---")

    print(" [4/8] DocSchema...")
    schema = DocSchema(
        project_id=project.id,
        version=2,
        name="Schema CERFA 13594 v2",
        document_type="CERFA_13594_02",
    )
    session.add(schema)
    await session.flush()
    print(f"       {schema}")

    print(" [5/8] FieldSpecs...")
    field_specs = []
    for i, (sec_id, sec_label, key, label, ftype, page, required, polygon) in enumerate(HARDCODED_FIELD_SPECS):
        fs = FieldSpec(
            schema_id=schema.id, page=page,
            section_id=sec_id, section_label=sec_label,
            field_key=key, display_label=label,
            value_type=ftype, required=required,
            display_order=i, polygon=polygon,
        )
        field_specs.append(fs)

    session.add_all(field_specs)
    await session.flush()
    print(f"       {len(field_specs)} FieldSpecs crees")

    await _seed_dataset_to_fields(
        session, project, schema, field_specs,
        file_path="/pvc/DIRES/cerfa/2026_01/2026_01_15_1321/cerfa_13594_sample.pdf",
        file_name="cerfa_13594_sample.pdf",
        raw_json=HARDCODED_RAW_JSON,
        ocr_values=HARDCODED_OCR_VALUES,
        document_id_str="cerfa_13594_sample",
        step_offset=6,
    )


# Mode 2 : Depuis JSON SMARTDOC


async def seed_from_smartdoc(
    session: AsyncSession, project: Project, json_path: Path
) -> None:
    from nota_core.schemas.interface_contract import SmartdocDocument

    print(f"\n --- Mode : SMARTDOC JSON ({json_path.name}) ---")

    with open(json_path, encoding="utf-8") as f:
        json_raw = json.load(f)

    smartdoc = SmartdocDocument.model_validate(json_raw)
    print(f"       JSON valide : {smartdoc.page_count} pages, document_id={smartdoc.document_id}")

    print(" [4/8] DocSchema...")
    schema = DocSchema(
        project_id=project.id,
        version=1,
        name="CERFA Surendettement",
        document_type="CERFA_SURENDETTEMENT",
    )
    session.add(schema)
    await session.flush()
    print(f"       {schema}")

    print(" [5/8] FieldSpecs (derives du JSON)...")
    specs_data = smartdoc.extract_field_specs()
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

    print(f"       {len(field_specs)} FieldSpecs crees depuis {smartdoc.page_count} pages")

    print(" [6/8] Dataset...")
    dataset = Dataset(
        project_id=project.id, schema_id=schema.id,
        name=CERFA_DATASET_NAME,
        ocr_provider=OcrProvider.PULSAR.value,
        status=DatasetStatus.ACTIVE.value,
        required_operators=2,
        configs={"confidence_threshold": 0.8},
    )
    session.add(dataset)
    await session.flush()
    print(f"       {dataset}")

    print(" [7/8] File + Document...")
    json_bytes = json.dumps(json_raw, ensure_ascii=False).encode("utf-8")
    sha256 = hashlib.sha256(json_bytes).hexdigest()

    file_ = File(
        file_path=f"/pvc/cerfa/surendettement/{smartdoc.document_id}.pdf",
        storage_type="pvc", mime_type="application/pdf",
        page_count=smartdoc.page_count,
        file_size_bytes=len(json_bytes),
        sha256_checksum=sha256,
    )
    session.add(file_)
    await session.flush()

    document = Document(
        dataset_id=dataset.id, file_id=file_.id,
        file_name=f"{smartdoc.document_id}.pdf",
        metadata_={
            "smartdoc_version": smartdoc.smartdoc_version,
            "document_id": smartdoc.document_id,
            "coordinate_unit": smartdoc.coordinate_unit,
        },
        status=DocumentStatus.IN_PROGRESS.value,
    )
    session.add(document)
    await session.flush()
    print(f"       {file_}")
    print(f"       {document}")

    print(" [8/8] OcrResult + DocumentFields...")
    ocr_result = OcrResult(
        document_id=document.id, dataset_id=dataset.id,
        storage_mode=StorageMode.JSONB.value,
        raw_json=json_raw,
    )
    session.add(ocr_result)
    await session.flush()

    doc_fields = []
    skipped = 0
    for _, section, kv in smartdoc.iter_kv_pairs():
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
    print(f"       {len(doc_fields)} DocumentFields crees")
    if skipped:
        print(f"       {skipped} KVPairs ignores (FieldSpec manquant)")

    print(f"\n Resume : {len(field_specs)} FieldSpecs, {len(doc_fields)} DocumentFields, {smartdoc.page_count} pages")


# Helper partage


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
    print(f" [{step_offset}/8] Dataset...")
    dataset = Dataset(
        project_id=project.id, schema_id=schema.id,
        name=CERFA_DATASET_NAME,
        description="Premier lot de documents",
        ocr_provider=OcrProvider.PULSAR.value,
        status=DatasetStatus.ACTIVE.value,
        required_operators=2,
        configs={"confidence_threshold": 0.8, "export_format": "json_pdf"},
    )
    session.add(dataset)
    await session.flush()
    print(f"       {dataset}")

    print(f" [{step_offset + 1}/8] File + Document...")
    json_bytes = json.dumps(raw_json, ensure_ascii=False).encode("utf-8")
    sha256 = hashlib.sha256(json_bytes).hexdigest()

    file_ = File(
        file_path=file_path, storage_type="pvc",
        mime_type="application/pdf", page_count=raw_json.get("page_count", 2),
        file_size_bytes=len(json_bytes), sha256_checksum=sha256,
    )
    session.add(file_)
    await session.flush()

    document = Document(
        dataset_id=dataset.id, file_id=file_.id, file_name=file_name,
        metadata_={"source": "PVC", "lot": "2026-01", "reception_date": "2026-01-15"},
        status=DocumentStatus.IN_PROGRESS.value,
    )
    session.add(document)
    await session.flush()
    print(f"       {file_}")
    print(f"       {document}")

    print(f" [{step_offset + 2}/8] OcrResult + DocumentFields...")
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
    print(f"       {len(doc_fields)} DocumentFields crees")


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
            await seed_from_smartdoc(session, project, json_path)
        else:
            await seed_hardcoded(session, project)

        await session.commit()

    await get_engine().dispose()
    print("\n  Seed termine avec succes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed NOTA database")
    parser.add_argument("--reset", action="store_true", help="Vide les tables avant de seeder")
    parser.add_argument("--json", default=None, help="Chemin vers un fichier JSON SMARTDOC v0.3")
    args = parser.parse_args()

    json_path = None
    if args.json:
        json_path = Path(args.json)
        if not json_path.exists():
            json_path = Path(__file__).parent.parent / args.json
        if not json_path.exists():
            print(f"Fichier introuvable : {args.json}")
            sys.exit(1)

    print(SEPARATOR)
    print("Seed de la base de donnees")
    print(f"  Mode : {'SMARTDOC JSON' if json_path else 'Donnees hardcodees'}")
    print(SEPARATOR)
    asyncio.run(main(reset=args.reset, json_path=json_path))
    print(SEPARATOR)
