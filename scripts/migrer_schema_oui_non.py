"""
scripts/migrer_schema_oui_non.py
--------------------------------
Met une base existante au schema CERFA corrige, sans perdre l'annotation faite.

Deux defauts du schema, corriges dans cerfa_v2.py :

- une question Oui / Non etait deux booleens (« ..._oui » et « ..._non ») :
  l'IHM posait la question deux fois. Elle devient UN booleen, vrai pour Oui,
  faux pour Non ;
- « Nom et adresse du creancier » (une seule case sur le CERFA) etait deux
  champs texte : l'OCR mettait tout dans le premier. Ils deviennent un champ.

Pour chaque paire, dans chaque schema, ligne de tableau par ligne de tableau :

- le premier champ de la paire est garde et renomme (field_key, libelle,
  description repris de cerfa_v2.py) ; le second est supprime ;
- sur chaque document, les deux valeurs sont fusionnees (valeur OCR, valeur
  retenue) : Oui coche -> vrai, Non coche -> faux, rien ou les deux -> vide ;
  nom et adresse -> « nom, adresse » ;
- les propositions humaines (la verite des benchmarks) suivent, job par job,
  avec la meme fusion : un document annote le reste ;
- les lignes de rapports de benchmark qui visaient un champ supprime le sont
  aussi (contrainte RESTRICT) : ces executions anterieures mesuraient
  l'ancien schema.

Sans --appliquer, rien n'est ecrit : le script dit ce qu'il ferait. Tout se
fait dans une transaction ; une erreur n'ecrit rien. Rejoue, il ne trouve
plus de paire et ne fait rien.

Le paquet *_core est trouve sous src/ : le script tourne tel quel dans adam et
dans nota, depuis la racine du depot (.env). cerfa_v2.py doit etre a jour.

Usage :
    python scripts/migrer_schema_oui_non.py              # ce qui serait fait
    python scripts/migrer_schema_oui_non.py --appliquer
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def _prefixe() -> str:
    cores = sorted(p.name for p in SRC.glob("*_core") if (p / "models").is_dir())
    if len(cores) != 1:
        raise SystemExit(f"attendu un *_core sous src/, trouve {cores}")
    return cores[0].removesuffix("_core")


def _module(nom: str) -> Any:
    return importlib.import_module(f"{_prefixe()}_{nom}")


# -- Fusion des valeurs ---------------------------------------------------------

_VRAI = {"true", "1", "oui", "x", "vrai", "yes"}


def _coche(valeur: Optional[str]) -> bool:
    return valeur is not None and str(valeur).strip().lower() in _VRAI


def fusion_oui_non(oui: Optional[str], non: Optional[str]) -> Optional[str]:
    """Case Oui cochee -> "true" ; case Non cochee -> "false" ; sinon vide."""
    if _coche(oui) and not _coche(non):
        return "true"
    if _coche(non) and not _coche(oui):
        return "false"
    return None


def fusion_texte(premier: Optional[str], second: Optional[str]) -> Optional[str]:
    """Nom et adresse, dans l'ordre du CERFA ; vide si les deux le sont."""
    morceaux = [str(v).strip() for v in (premier, second) if v is not None and str(v).strip()]
    return ", ".join(morceaux) or None


@dataclass(frozen=True)
class Regle:
    """Paire (garde, supprime) d'une section, et sa cle d'arrivee."""

    garde: str
    supprime: str
    nouvelle: str
    fusion: Callable[[Optional[str], Optional[str]], Optional[str]]


def regles(section_id: str, cles: List[str]) -> List[Regle]:
    """Les paires presentes parmi les cles d'une section."""
    presentes = set(cles)
    trouvees: List[Regle] = []
    for cle in cles:
        if cle.endswith("_oui") and f"{cle[:-4]}_non" in presentes:
            trouvees.append(Regle(cle, f"{cle[:-4]}_non", cle[:-4], fusion_oui_non))
        elif cle == "oui" and "non" in presentes and section_id == "dossier_precedent":
            trouvees.append(Regle("oui", "non", "depose", fusion_oui_non))
    for qui in ("creancier", "banque"):
        if f"nom_{qui}" in presentes and f"adresse_{qui}" in presentes:
            trouvees.append(
                Regle(f"nom_{qui}", f"adresse_{qui}", f"nom_adresse_{qui}", fusion_texte)
            )
    return trouvees


# -- Migration ------------------------------------------------------------------

_RANG_STATUT = {"CORRECTED": 3, "VALIDATED": 2, "DISPUTED": 1, "PENDING": 0}


async def migrer(appliquer: bool) -> None:
    from sqlalchemy import delete, select

    m = _module("core.models")
    session_mod = _module("core.db.session")
    cerfa = _module("core.schemas.cerfa_v2")
    definitions: Dict[str, Any] = {
        cle: definition
        for champs in cerfa.CERFA_V2_PAGE_FIELDS.values()
        for cle, definition in champs.items()
    }
    FieldSpec, DocumentField, FieldProposal = m.FieldSpec, m.DocumentField, m.FieldProposal
    EvaluationReport = m.EvaluationReport

    compte: Counter = Counter()
    exemples: List[str] = []
    async with session_mod.get_async_session() as db:
        specs = (await db.execute(select(FieldSpec).order_by(FieldSpec.id))).scalars().all()
        # (schema, section, ligne) -> {field_key: FieldSpec}
        par_groupe: Dict[Tuple[int, str, Optional[str]], Dict[str, Any]] = defaultdict(dict)
        for spec in specs:
            par_groupe[(spec.schema_id, spec.section_id, spec.group_id)][spec.field_key] = spec

        for (schema_id, section_id, group_id), champs in par_groupe.items():
            for regle in regles(section_id, list(champs)):
                garde, supprime = champs[regle.garde], champs[regle.supprime]
                await _fusionner_champs(db, m, garde, supprime, regle, compte)
                definition = definitions.get(f"{section_id}.{regle.nouvelle}")
                if definition is None:
                    raise SystemExit(
                        f"{section_id}.{regle.nouvelle} absent de cerfa_v2.py : copiez d'abord "
                        "la version corrigee du schema, puis relancez."
                    )
                libelle = definition["description"]
                suffixe = garde.display_label.rsplit(" - ", 1)[1] if group_id else None
                if len(exemples) < 6:
                    exemples.append(
                        f"  schema {schema_id} {section_id}{f'[{group_id}]' if group_id else ''} : "
                        f"{regle.garde} + {regle.supprime} -> {regle.nouvelle}"
                    )
                garde.field_key = regle.nouvelle
                garde.description = libelle
                garde.display_label = f"{libelle} - {suffixe}" if suffixe else libelle
                compte["rapports supprimes"] += (
                    await db.execute(
                        delete(EvaluationReport).where(
                            EvaluationReport.field_spec_id == supprime.id
                        )
                    )
                ).rowcount or 0
                await db.flush()
                await db.execute(
                    delete(FieldSpec)
                    .where(FieldSpec.id == supprime.id)
                    .execution_options(synchronize_session=False)
                )
                db.expunge(supprime)
                compte["paires"] += 1
                compte[f"paires {regle.fusion.__name__}"] += 1
        await db.flush()

        print("Exemples :")
        print("\n".join(exemples) or "  aucun")
        print("\nBilan :")
        if not compte["paires"]:
            print("  aucune paire : la base est deja au schema corrige.")
        for cle in (
            "paires",
            "paires fusion_oui_non",
            "paires fusion_texte",
            "champs de document fusionnes",
            "valeurs retenues renseignees",
            "propositions deplacees",
            "propositions fusionnees",
            "conflits (Oui et Non coches)",
            "rapports supprimes",
        ):
            print(f"  {cle:<32} {compte[cle]}")
        if not appliquer:
            await db.rollback()
            print("\n(sans --appliquer) rien n'est ecrit.")
            return
    print("\nBase migree.")


async def _fusionner_champs(
    db: Any, m: Any, garde: Any, supprime: Any, regle: Regle, compte: Counter
) -> None:
    """Fusionne, document par document, le champ supprime dans le champ garde."""
    from sqlalchemy import delete, select

    DocumentField, FieldProposal = m.DocumentField, m.FieldProposal
    lignes = (
        (
            await db.execute(
                select(DocumentField).where(
                    DocumentField.field_spec_id.in_([garde.id, supprime.id])
                )
            )
        )
        .scalars()
        .all()
    )
    par_document: Dict[Tuple[int, Optional[str]], Dict[int, Any]] = defaultdict(dict)
    for df in lignes:
        par_document[(df.document_id, df.group_id)][df.field_spec_id] = df

    for champs in par_document.values():
        a, b = champs.get(garde.id), champs.get(supprime.id)
        if a is None:
            # Seul le second existe : il devient le champ garde.
            b.field_spec_id = garde.id
            a, b = b, None
            a.ocr_value = regle.fusion(None, a.ocr_value)
            a.resolved_value = regle.fusion(None, a.resolved_value)
            await _fusionner_propositions(db, m, a, None, regle, compte, seul_second=True)
            compte["champs de document fusionnes"] += 1
            continue
        if b is None:
            a.ocr_value = regle.fusion(a.ocr_value, None)
            a.resolved_value = regle.fusion(a.resolved_value, None)
            await _fusionner_propositions(db, m, a, None, regle, compte)
            continue
        if regle.fusion is fusion_oui_non and _coche(a.resolved_value) and _coche(b.resolved_value):
            compte["conflits (Oui et Non coches)"] += 1
        a.ocr_value = regle.fusion(a.ocr_value, b.ocr_value)
        a.resolved_value = regle.fusion(a.resolved_value, b.resolved_value)
        if a.resolved_value is not None:
            compte["valeurs retenues renseignees"] += 1
        if _RANG_STATUT.get(str(b.status), 0) > _RANG_STATUT.get(str(a.status), 0):
            a.status = b.status
            a.resolved_by = b.resolved_by or a.resolved_by
        confiances = [c for c in (a.ocr_confidence, b.ocr_confidence) if c is not None]
        a.ocr_confidence = min(confiances) if confiances else None
        a.consensus_reached = bool(a.consensus_reached or b.consensus_reached)
        if a.ocr_polygon is None:
            a.ocr_polygon = b.ocr_polygon
        await _fusionner_propositions(db, m, a, b, regle, compte)
        await db.flush()
        # SQL direct : l'ORM viderait le lien des propositions au lieu de les
        # supprimer. Celles qui restent sur b sont fusionnees dans celles de a.
        for table, colonne in (
            (FieldProposal, FieldProposal.document_field_id),
            (DocumentField, DocumentField.id),
        ):
            await db.execute(
                delete(table).where(colonne == b.id).execution_options(synchronize_session=False)
            )
        db.expunge(b)
        compte["champs de document fusionnes"] += 1


async def _fusionner_propositions(
    db: Any,
    m: Any,
    a: Any,
    b: Optional[Any],
    regle: Regle,
    compte: Counter,
    seul_second: bool = False,
) -> None:
    """Job par job, la derniere proposition de chaque champ, fusionnees."""
    from sqlalchemy import select

    FieldProposal = m.FieldProposal
    ids = [a.id] + ([b.id] if b is not None else [])
    propositions = (
        (
            await db.execute(
                select(FieldProposal)
                .where(FieldProposal.document_field_id.in_(ids))
                .order_by(FieldProposal.created_at, FieldProposal.id)
            )
        )
        .scalars()
        .all()
    )
    par_job: Dict[int, Dict[int, Any]] = defaultdict(dict)
    for p in propositions:
        par_job[p.job_id][p.document_field_id] = p  # la derniere l'emporte
    for derniers in par_job.values():
        pa = derniers.get(a.id)
        pb = derniers.get(b.id) if b is not None else None
        if seul_second:
            pa.value = regle.fusion(None, pa.value)
            compte["propositions fusionnees"] += 1
        elif pa is not None:
            pa.value = regle.fusion(pa.value, pb.value if pb is not None else None)
            compte["propositions fusionnees"] += 1
        elif pb is not None:
            pb.document_field_id = a.id
            pb.value = regle.fusion(None, pb.value)
            compte["propositions deplacees"] += 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--appliquer", action="store_true", help="Ecrire (sinon : apercu)")
    args = parser.parse_args()
    if os.environ.get("POSTGRES_DB"):
        print(f"POSTGRES_DB={os.environ.pop('POSTGRES_DB')} du terminal ignore : base du .env")
    core = _module("core.core.config").get_core_settings()
    _module("core.db.session").init_engine(core.async_database_url, echo=False)
    print(f"Base : {core.postgres_db}\n")
    asyncio.run(migrer(args.appliquer))


if __name__ == "__main__":
    main()
