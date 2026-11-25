"""
scripts/seed_study.py
---------------------
Importe la planilha de l'etude (50 CERFA remplis) comme un dataset pret et valide.

Deux etapes, pour pouvoir relire le JSON avant d'ecrire en base :

    convert : planilha (.xlsx, ou .tsv au format de study.md) -> study.json
              Aucun acces base. Affiche les colonnes non reconnues et les valeurs
              corrigees : c'est la qu'on itere sur le mapping (ALIASES ci-dessous).
    load    : study.json + dossier de PDF -> nouveau dataset en base. Pour chaque
              document : copie du PDF sur le PVC, File, Document VALIDATED, et un
              DocumentField VALIDATED par FieldSpec (vide si la planilha ne dit rien).

Usage :
    python scripts/seed_study.py convert etude.xlsx -o study.json
    python scripts/seed_study.py load study.json --pdf-dir ./pdfs --project-id 1
    python scripts/seed_study.py load study.json --pdf-dir ./pdfs --project-id 1 --dry-run

Une planilha .xlsx demande openpyxl, hors des dependances du projet :
    uv run --with openpyxl python scripts/seed_study.py convert etude.xlsx -o study.json

Chaque `load` cree un nouveau dataset. Un PDF deja en base (meme empreinte) n'est
pas recopie : son File est reutilise.

Format de la planilha : un onglet d'index (file_name, doc_id, ...) et un onglet par
page nommé « PAGE n ». Premiere colonne doc_id ; une colonne group_id optionnelle ;
les autres colonnes sont « section.champ ». Une ligne par document, ou par ligne de
tableau repetable (group_id = dette_logement_1, vehicule_1...).
"""

import argparse
import asyncio
import importlib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _module(nom: str) -> Any:
    """adam_<nom> ou nota_<nom> : le script se copie tel quel d'un depot a l'autre."""
    cores = sorted(p.name for p in SRC.glob("*_core") if (p / "models").is_dir())
    if len(cores) != 1:
        raise SystemExit(f"attendu un *_core sous src/, trouve {cores}")
    return importlib.import_module(f"{cores[0].removesuffix('_core')}_{nom}")


CERFA_V2_PAGE_FIELDS = _module("core.schemas.cerfa_v2").CERFA_V2_PAGE_FIELDS
from seed_schema_cerfa import REPEATABLE_SECTIONS  # noqa: E402

CERFA_DOCUMENT_TYPE = "CERFA_SURENDETTEMENT_V2"  # seed.py
CERFA_PAGE_COUNT = 12  # seed.py


def schema_group(section: str, group: str) -> Optional[str]:
    """group_id du schema pour celui de la planilha : seul le numero compte.

    La planilha dit dette_conso_1 ou decouverts_bancaires_1 la ou le schema dit
    pret_1 ou compte_1 ; on garde le numero final et on reprend le prefixe du schema.
    """
    number = re.search(r"(\d+)\s*$", group)
    if not number:
        return None
    return f"{REPEATABLE_SECTIONS[section][1]}_{int(number.group(1))}"


# --------------------------------------------------------------------------- mapping
# Colonne de la planilha -> cle du schema. Le generique (« deposant.x » ->
# « deposant_x », paires _oui/_non) couvre l'essentiel ; ceci ne garde que les ecarts.

#: Rubriques renommees : planilha -> schema.
SECTION_ALIASES = {
    "situation_logemen_co_deposant": "situation_logement_co_deposant",  # typo de la planilha
    "dettes_pension_amendes_condamnations": "dettes_pension_amendes",
    "autre_patrimoine": "patrimoine",
    "aucun_patrimoine": "patrimoine",
}

#: Sous-blocs de patrimoine_immobilier.
PATRIMOINE_SUB = {
    "autre_bien_immobilier_1": "autre_bien_1",
    "autre_bien_immobilier_2": "autre_bien_2",
    "mobil_home_caravane": "mobil_home",
    "garage_parking": "garage",
}

#: Champs renommes, quelle que soit la rubrique (apres retrait de _oui/_non).
FIELD_ALIASES = {
    "valeur_estimee": "valeur",
    "perp_perco": "per",
    "impots_revenu": "impot_revenu",
    "frais_maison_retraite_autres": "frais_maison_retraite",
    "sdf": "sans_domicile_fixe",
    "montant_decouvert_utilise": "montant_decouvert",
    "date_debut_contrat": "date_debut",
    "nombre_loyers_prevus": "nombre_loyers",
    "personne_societe_cautionnee": "personne_cautionnee",
    "mensualite_hors_assurance": "mensualite",
    "signature_co_deposant": "signature_codeposant",
    "principale": "texte",
    "profession_dernier_emploi": "profession",
    "pensions_retraite": "retraite",
    "allocation_logement_apl": "allocation_logement",
    "allocation_specifique_solidarite": "allocation_solidarite_specifique",
    "revenu_solidarite_active": "rsa",
    "revenus_valeurs_capitaux_mobiliers": "revenus_capitaux_mobiliers",
    "autres": "autres_ressources",
}

#: Cas qui ne se deduisent pas : colonne complete -> cle complete du schema.
ALIASES = {
    "dossier_precedent.oui": "dossier_precedent.depose",
    "dossier_precedent.non": "dossier_precedent.depose",
    "decouverts_bancaires.nom_adresse": "decouverts_bancaires.nom_adresse_banque",
    "credits_immobiliers.nom_adresse": "credits_immobiliers.nom_adresse_creancier",
    "credits_immobiliers.adresse_assureur": "credits_immobiliers.nom_assureur",
    "aucun_patrimoine.aucun_patrimoine": "patrimoine.aucun",
    "gestion_budget.compte_oui": "gestion_budget.compte_bancaire",
    "gestion_budget.compte_non": "gestion_budget.compte_bancaire",
    "autre_patrimoine.precision": "patrimoine.autre_precision",
}

#: Colonnes a ignorer sans bruit.
IGNORED: Set[str] = set()


def _candidates(column: str) -> List[Tuple[str, Optional[bool]]]:
    """Cles de schema possibles pour une colonne, avec le sens oui/non si pertinent.

    Le second element vaut True pour une colonne « _oui », False pour « _non »,
    None pour une colonne ordinaire.
    """
    if column in ALIASES:
        target = ALIASES[column]
        sense = (
            True
            if column.endswith((".oui", "_oui"))
            else False if column.endswith((".non", "_non")) else None
        )
        return [(target, sense)]
    out: List[Tuple[str, Optional[bool]]] = [(column, None)]
    section, _, rest = column.partition(".")
    section = SECTION_ALIASES.get(section, section)
    sense: Optional[bool] = None
    for suffix, value in (("_oui", True), ("_non", False)):
        if rest.endswith(suffix):
            rest, sense = rest[: -len(suffix)], value
    parts = rest.split(".")
    parts = [PATRIMOINE_SUB.get(p, p) for p in parts]
    parts[-1] = FIELD_ALIASES.get(parts[-1], parts[-1])
    joined = "_".join(parts)  # deposant.loyer -> deposant_loyer
    for key in (rest, ".".join(parts), joined):
        out.append((f"{section}.{key}", sense))
    # situation_professionnelle.deposant.cdi -> deposant_statut_cdi
    out.append((f"{section}.{'_'.join(parts[:-1] + ['statut_' + parts[-1]])}", sense))
    # nom_adresse -> nom_adresse_creancier
    out.append((f"{section}.{joined}_creancier", sense))
    out.append((f"{section}.{joined}_banque", sense))
    return out


def resolve(page: int, column: str) -> Optional[Tuple[str, Optional[bool]]]:
    keys = CERFA_V2_PAGE_FIELDS.get(page, {})
    for key, sense in _candidates(column):
        if key in keys:
            # Une colonne « civilite_monsieur » existe telle quelle : pas de sens oui/non.
            return key, sense
    return None


# --------------------------------------------------------------------------- valeurs
_DATE_FR = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")
_DATE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def normalize(
    raw: str, field_def: Dict[str, Any], sense: Optional[bool], warn: Any
) -> Optional[str]:
    """Valeur au format que le back stocke : bool true/false, nombre 12.5, date ISO."""
    if raw == "":
        return None
    kind = field_def.get("type", "string")
    if kind == "boolean":
        truthy = raw.lower() in {"1", "true", "oui", "x", "yes"}
        falsy = raw.lower() in {"0", "false", "non", "no"}
        if not (truthy or falsy):
            warn(f"booleen illisible {raw!r}")
            return None
        if sense is False:  # colonne « _non » : cochee => false ; decochee => rien
            return "false" if truthy else "true"
        return "true" if truthy else "false"
    if kind == "number":
        match = _NUMBER.search(raw)
        if not match:
            warn(f"nombre illisible {raw!r}")
            return None
        if match.group(0) != raw.replace(" ", ""):
            warn(f"nombre {raw!r} lu comme {match.group(0)}")
        return match.group(0).replace(",", ".")
    if field_def.get("format") == "date":
        fr = _DATE_FR.match(raw)
        if fr:
            d, m, y = (int(x) for x in fr.groups())
            return f"{y:04d}-{m:02d}-{d:02d}"
        iso = _DATE_ISO.match(raw)
        if iso:
            return "-".join(iso.groups())
        warn(f"date illisible {raw!r}")
        return raw
    return raw


# --------------------------------------------------------------------------- lecture
Table = Tuple[List[str], List[List[str]]]


def _read_xlsx(path: Path) -> Tuple[Table, Dict[int, Table]]:
    try:
        import openpyxl
    except ImportError:
        sys.exit(
            "openpyxl manquant : uv run --with openpyxl python scripts/seed_study.py ... "
            "(ou fournir un .tsv)"
        )
    book = openpyxl.load_workbook(path, data_only=True, read_only=True)
    index: Optional[Table] = None
    pages: Dict[int, Table] = {}
    for sheet in book.worksheets:
        rows = [[_clean(c) for c in row] for row in sheet.iter_rows(values_only=True)]
        rows = [r for r in rows if any(r)]
        if not rows:
            continue
        m = re.match(r"\s*page\s*(\d+)", sheet.title, re.I)
        if m:
            pages[int(m.group(1))] = (rows[0], rows[1:])
        elif "doc_id" in rows[0] and "file_name" in rows[0]:
            index = (rows[0], rows[1:])
    if index is None:
        sys.exit("onglet d'index (colonnes file_name, doc_id) introuvable")
    return index, pages


def _read_tsv(path: Path) -> Tuple[Table, Dict[int, Table]]:
    """Format de study.md : bloc d'index, puis des sections « PAGE n »."""
    blocks = re.split(r"^---\s*$", path.read_text(encoding="utf-8"), flags=re.M)
    index: Optional[Table] = None
    pages: Dict[int, Table] = {}
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        m = re.match(r"\s*page\s*(\d+)\s*$", lines[0], re.I)
        if m:
            rows = [[c.strip() for c in ln.split("\t")] for ln in lines[1:]]
            pages[int(m.group(1))] = (rows[0], rows[1:])
        elif lines[0].startswith("file_name"):
            rows = [[c.strip() for c in ln.split("\t")] for ln in lines]
            index = (rows[0], rows[1:])
    if index is None:
        sys.exit("bloc d'index (file_name, doc_id) introuvable")
    return index, pages


def _doc_key(value: str) -> int:
    return int(float(value))


def convert(source: Path, output: Path) -> None:
    (index_head, index_rows), pages = (
        _read_xlsx(source) if source.suffix.lower() in {".xlsx", ".xlsm"} else _read_tsv(source)
    )
    name_col, id_col = index_head.index("file_name"), index_head.index("doc_id")
    files = {_doc_key(r[id_col]): r[name_col] for r in index_rows if len(r) > id_col and r[id_col]}
    docs: Dict[int, Dict[Tuple[str, Optional[str], str], str]] = {}
    warnings: List[str] = []
    unknown: Dict[str, Set[int]] = {}

    for page, (head, rows) in sorted(pages.items()):
        group_col = head.index("group_id") if "group_id" in head else None
        schema = CERFA_V2_PAGE_FIELDS.get(page, {})
        plan: Dict[int, Tuple[str, Optional[bool]]] = {}
        for i, column in enumerate(head):
            if i == 0 or i == group_col or not column or column in IGNORED:
                continue
            hit = resolve(page, column)
            if hit:
                plan[i] = hit
            else:
                unknown.setdefault(column, set()).add(page)
        for row in rows:
            if not row or not row[0]:
                continue
            doc = _doc_key(row[0])
            group = row[group_col].strip() if group_col is not None and len(row) > group_col else ""
            for i, (key, sense) in plan.items():
                raw = row[i].strip() if i < len(row) else ""
                where = f"page {page}, doc {doc:02d}, {head[i]}"
                section = key.partition(".")[0]
                value = normalize(
                    raw, schema[key], sense, lambda m, w=where: warnings.append(f"{w}: {m}")
                )
                if value is None:
                    continue
                field_key = key.partition(".")[2]
                # Le group_id de la ligne ne vaut que pour les rubriques repetables :
                # une ligne « vehicule_1 » porte aussi des charges qui n'en ont pas.
                spec_group = None
                if section in REPEATABLE_SECTIONS:
                    spec_group = schema_group(section, group)
                    if spec_group is None:
                        warnings.append(f"{where}: rubrique repetable sans group_id, valeur ignoree")
                        continue
                docs.setdefault(doc, {})[(section, spec_group, field_key)] = value

    out = {
        "documents": [
            {
                "doc_id": doc,
                "file_name": files.get(doc, ""),
                "fields": [
                    {"section_id": s, "group_id": g, "field_key": f, "value": v}
                    for (s, g, f), v in sorted(
                        values.items(), key=lambda kv: (kv[0][0], kv[0][1] or "", kv[0][2])
                    )
                ],
            }
            for doc, values in sorted(docs.items())
        ]
    }
    output.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(
        f"{len(out['documents'])} documents, {sum(len(d['fields']) for d in out['documents'])} valeurs -> {output}"
    )
    for doc in out["documents"]:
        if not doc["file_name"]:
            print(f"  doc {doc['doc_id']:02d} : pas de file_name dans l'index (ne sera pas charge)")
    for column, pgs in sorted(unknown.items()):
        print(f"  COLONNE NON RECONNUE (pages {sorted(pgs)}) : {column}")
    for w in warnings:
        print(f"  valeur : {w}")


# --------------------------------------------------------------------------- base
async def load(args: argparse.Namespace) -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    api_settings = _module("api.core.config").settings
    CoreSettings = _module("core.core.config").CoreSettings
    session_mod = _module("core.db.session")
    get_engine, init_engine = session_mod.get_engine, session_mod.init_engine
    OcrProvider = _module("core.enums.ocr").OcrProvider
    status = _module("core.enums.status")
    DatasetStatus, DocumentFieldStatus, DocumentStatus = (
        status.DatasetStatus,
        status.DocumentFieldStatus,
        status.DocumentStatus,
    )
    models = _module("core.models")
    Dataset, DocSchema, Document = models.Dataset, models.DocSchema, models.Document
    DocumentField, FieldSpec, File = models.DocumentField, models.FieldSpec, models.File
    Organisation, Project = models.Organisation, models.Project
    sha256_bytes = _module("core.utils.hashing").sha256_bytes
    pdf_render = _module("core.utils.pdf_render")

    data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    pdf_dir = Path(args.pdf_dir)
    pdfs = {p.name: p for p in pdf_dir.rglob("*.pdf")}

    todo = []
    for doc in data["documents"]:
        name = doc["file_name"]
        if not name:
            print(f"  doc {doc['doc_id']:02d} ignore : pas de file_name")
        elif name not in pdfs:
            print(f"  doc {doc['doc_id']:02d} ignore : {name} absent de {pdf_dir}")
        else:
            todo.append((doc, pdfs[name]))
    print(f"{len(todo)} documents a charger sur {len(data['documents'])}")
    if args.dry_run or not todo:
        return

    init_engine(CoreSettings().async_database_url, echo=False)
    factory = async_sessionmaker(bind=get_engine(), expire_on_commit=False)
    async with factory() as session:
        projet = (
            await session.execute(
                select(Project, Organisation)
                .join(Organisation, Organisation.id == Project.organisation_id)
                .where(Project.id == args.project_id)
            )
        ).first()
        if projet is None:
            sys.exit(f"projet {args.project_id} introuvable")
        # Seuls les agents de cette organisation verront le dataset.
        print(f"projet {args.project_id} : {projet[0].name} (organisation {projet[1].slug})")
        schema = (
            (
                await session.execute(
                    select(DocSchema)
                    .where(DocSchema.project_id == args.project_id)
                    .where(DocSchema.document_type == CERFA_DOCUMENT_TYPE)
                    .order_by(DocSchema.id.desc())
                )
            )
            .scalars()
            .first()
        )
        if schema is None:
            sys.exit(
                "aucun schema CERFA dans ce projet : lancer scripts/seed_schema_cerfa.py d'abord"
            )
        specs = list(
            (
                await session.execute(select(FieldSpec).where(FieldSpec.schema_id == schema.id))
            ).scalars()
        )
        by_key = {(s.section_id, s.group_id, s.field_key): s for s in specs}

        dataset = Dataset(
            project_id=args.project_id,
            schema_id=schema.id,
            name=args.name,
            description="Etude : CERFA remplis et valides, pour tester Nota",
            ocr_provider=OcrProvider.MISTRAL.value,
            status=DatasetStatus.ACTIVE.value,
            required_operators=2,
            expected_page_count=CERFA_PAGE_COUNT,
            configs={"confidence_threshold": 0.8, "export_format": "json_pdf"},
        )
        session.add(dataset)
        await session.flush()
        print(f"dataset {dataset.id} : {dataset.name} (schema {schema.id}, {len(specs)} champs)")

        pvc = Path(api_settings.pvc_mount_path)
        for doc, pdf in todo:
            pdf_bytes = pdf.read_bytes()
            checksum = sha256_bytes(pdf_bytes)
            # sha256_checksum est unique : un PDF deja charge (relance) reprend son File.
            file_ = (
                await session.execute(select(File).where(File.sha256_checksum == checksum))
            ).scalar_one_or_none()
            if file_ is None:
                relative = Path("study") / f"{doc['doc_id']:02d}_{pdf.name}"
                destination = pvc / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(pdf_bytes)
                file_ = File(
                    file_path=relative.as_posix(),
                    storage_type="pvc",
                    mime_type="application/pdf",
                    page_count=0,
                    file_size_bytes=len(pdf_bytes),
                    sha256_checksum=checksum,
                )
                session.add(file_)
                await session.flush()
            # Le worker d'images ne traite que les documents RECEIVED : un document
            # VALIDATED n'aurait aucune page affichable. On les rend ici.
            pages_dir = pvc / pdf_render.pages_relative_dir(file_.id)
            if not (pages_dir / pdf_render.page_image_filename(1)).is_file():
                written = pdf_render.render_pages_to_png(pvc / file_.file_path, pages_dir)
                file_.page_count = len(written)
            document = Document(
                dataset_id=dataset.id,
                file_id=file_.id,
                file_name=pdf.name,
                metadata_={"source": "study", "study_doc_id": doc["doc_id"]},
                status=DocumentStatus.VALIDATED.value,
            )
            session.add(document)
            await session.flush()

            values = {
                (f["section_id"], f["group_id"], f["field_key"]): f["value"] for f in doc["fields"]
            }
            missing = [k for k in values if k not in by_key]
            for key in missing:
                print(f"  doc {doc['doc_id']:02d} : pas de FieldSpec pour {key}, valeur perdue")
            session.add_all(
                DocumentField(
                    document_id=document.id,
                    field_spec_id=spec.id,
                    group_id=spec.group_id,
                    ocr_value=None,
                    resolved_value=values.get(key),
                    status=DocumentFieldStatus.VALIDATED.value,
                    consensus_reached=True,
                )
                for key, spec in by_key.items()
            )
            await session.flush()
            print(
                f"  doc {doc['doc_id']:02d} -> document {document.id}, {len(values) - len(missing)} valeurs"
            )
        await session.commit()
    await get_engine().dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert", help="planilha -> JSON")
    c.add_argument("source")
    c.add_argument("-o", "--output", default="study.json")
    ld = sub.add_parser("load", help="JSON + PDF -> dataset en base")
    ld.add_argument("json")
    ld.add_argument("--pdf-dir", required=True)
    ld.add_argument("--project-id", type=int, required=True)
    ld.add_argument("--name", default="Etude 50 CERFA")
    ld.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.cmd == "convert":
        convert(Path(args.source), Path(args.output))
    else:
        asyncio.run(load(args))


if __name__ == "__main__":
    main()
