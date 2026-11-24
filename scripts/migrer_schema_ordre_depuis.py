"""
scripts/migrer_schema_ordre_depuis.py
-------------------------------------
Met une base existante au schema CERFA de cerfa_v2.py, sans perdre l'annotation.

A lancer APRES migrer_schema_oui_non.py. Trois changements :

- page 3 : une date « depuis le » par case de statut, juste apres elle, au
  lieu d'une seule date par colonne. Sur chaque document, l'ancienne date va
  a la case cochee ; si plusieurs cases le sont, a la premiere (le script
  liste ces documents : a revoir dans l'IHM). Les propositions humaines
  suivent, job par job : un document annote le reste ;
- ordre d'affichage aligne sur le CERFA : gestion du budget avant les
  vehicules (page 4), cause du surendettement en fin de page 11 ;
- libelles et descriptions repris de cerfa_v2.py (signatures, etc.).

Sans --appliquer, rien n'est ecrit. Tout se fait dans une transaction.
Rejoue, il ne trouve plus rien a faire.

Usage :
    python scripts/migrer_schema_ordre_depuis.py              # apercu
    python scripts/migrer_schema_ordre_depuis.py --appliquer
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import importlib.util
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

_SECTION = "situation_professionnelle"
_PERSONNES = ("deposant", "co_deposant")
_VRAI = {"true", "1", "oui", "x", "vrai", "yes"}


def _prefixe() -> str:
    cores = sorted(p.name for p in SRC.glob("*_core") if (p / "models").is_dir())
    if len(cores) != 1:
        raise SystemExit(f"attendu un *_core sous src/, trouve {cores}")
    return cores[0].removesuffix("_core")


def _module(nom: str) -> Any:
    return importlib.import_module(f"{_prefixe()}_{nom}")


def _seed() -> Any:
    spec = importlib.util.spec_from_file_location(
        "seed_cerfa", ROOT / "scripts/seed_schema_cerfa.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _coche(valeur: Optional[str]) -> bool:
    return valeur is not None and str(valeur).strip().lower() in _VRAI


def cible_date(statuts: List[str], valeurs: Dict[str, Optional[str]]) -> Tuple[Optional[str], int]:
    """La case qui recoit l'ancienne date : la premiere cochee, et le nombre de cochees."""
    cochees = [s for s in statuts if _coche(valeurs.get(s))]
    return (cochees[0] if cochees else None), len(cochees)


async def migrer(appliquer: bool) -> None:
    from sqlalchemy import delete, select

    m = _module("core.models")
    session_mod = _module("core.db.session")
    attendus = {(s["section_id"], s["group_id"], s["field_key"]): s for s in _seed().build_specs()}
    FieldSpec, DocumentField, FieldProposal = m.FieldSpec, m.DocumentField, m.FieldProposal

    compte: Counter = Counter()
    a_revoir: List[str] = []
    async with session_mod.get_async_session() as db:
        specs = (await db.execute(select(FieldSpec))).scalars().all()
        par_schema: Dict[int, Dict[Tuple[str, Optional[str], str], Any]] = defaultdict(dict)
        for spec in specs:
            par_schema[spec.schema_id][(spec.section_id, spec.group_id, spec.field_key)] = spec

        for schema_id, champs in par_schema.items():
            if not any(k[0] == _SECTION for k in champs):
                continue  # pas un schema CERFA
            if any(k[2].endswith(("_oui", "_non")) for k in champs):
                raise SystemExit(
                    f"schema {schema_id} : paires Oui/Non encore presentes. Lancez d'abord "
                    "migrer_schema_oui_non.py --appliquer."
                )
            for personne in _PERSONNES:
                ancienne = champs.get((_SECTION, None, f"{personne}_depuis"))
                if ancienne is None:
                    continue
                statuts = sorted(
                    (
                        k[2]
                        for k in attendus
                        if k[0] == _SECTION
                        and k[2].startswith(f"{personne}_statut_")
                        and k[2].endswith("_depuis")
                    ),
                    key=lambda cle: attendus[(_SECTION, None, cle)]["display_order"],
                )
                nouvelles: Dict[str, Any] = {}
                for cle in statuts:
                    target_of = attendus[(_SECTION, None, cle)]
                    spec = champs.get((_SECTION, None, cle))
                    if spec is None:
                        spec = FieldSpec(
                            schema_id=schema_id,
                            page=target_of["page"],
                            section_id=_SECTION,
                            section_label=ancienne.section_label,
                            group_id=None,
                            field_key=cle,
                            display_label=target_of["display_label"],
                            description=target_of["description"],
                            value_type=target_of["value_type"],
                            required=False,
                            sensitive=False,
                            display_order=target_of["display_order"],
                        )
                        db.add(spec)
                        compte["champs de schema crees"] += 1
                    nouvelles[cle.removesuffix("_depuis")] = spec
                await db.flush()
                ids_statut = {
                    champs[(_SECTION, None, s)].id: s
                    for s in nouvelles
                    if (_SECTION, None, s) in champs
                }
                ordre = list(nouvelles)
                await _deplacer_dates(
                    db, m, schema_id, ancienne, nouvelles, ids_statut, ordre, compte, a_revoir
                )
                await db.execute(
                    delete(m.EvaluationReport).where(
                        m.EvaluationReport.field_spec_id == ancienne.id
                    )
                )
                await db.execute(
                    delete(FieldSpec)
                    .where(FieldSpec.id == ancienne.id)
                    .execution_options(synchronize_session=False)
                )
                db.expunge(ancienne)
                compte["anciennes dates supprimees"] += 1

            # Ordre, page, libelles : ceux de cerfa_v2.py.
            actuels = (
                (await db.execute(select(FieldSpec).where(FieldSpec.schema_id == schema_id)))
                .scalars()
                .all()
            )
            for spec in actuels:
                target_of = attendus.get((spec.section_id, spec.group_id, spec.field_key))
                if target_of is None:
                    compte["champs hors cerfa_v2.py (laisses tels quels)"] += 1
                    continue
                avant = (spec.display_order, spec.page, spec.display_label, spec.description)
                spec.display_order = target_of["display_order"]
                spec.page = target_of["page"]
                spec.display_label = target_of["display_label"]
                spec.description = target_of["description"]
                if avant != (spec.display_order, spec.page, spec.display_label, spec.description):
                    compte["champs remis en ordre ou renommes"] += 1
            compte["schemas"] += 1
        await db.flush()

        print("Bilan :")
        for cle in (
            "schemas",
            "champs de schema crees",
            "anciennes dates supprimees",
            "champs de document crees",
            "dates deplacees",
            "propositions creees",
            "champs remis en ordre ou renommes",
            "champs hors cerfa_v2.py (laisses tels quels)",
        ):
            print(f"  {cle:<46} {compte[cle]}")
        if a_revoir:
            print("\nPlusieurs statuts coches, date mise sur le premier (a verifier dans l'IHM) :")
            print("\n".join(a_revoir))
        if not appliquer:
            await db.rollback()
            print("\n(sans --appliquer) rien n'est ecrit.")
            return
    print("\nBase migree.")


async def _deplacer_dates(
    db: Any,
    m: Any,
    schema_id: int,
    ancienne: Any,
    nouvelles: Dict[str, Any],
    ids_statut: Dict[int, str],
    ordre: List[str],
    compte: Counter,
    a_revoir: List[str],
) -> None:
    """Document par document : une ligne par nouvelle date, l'ancienne va a la case cochee."""
    from sqlalchemy import delete, select

    DocumentField, FieldProposal = m.DocumentField, m.FieldProposal
    anciens = (
        (await db.execute(select(DocumentField).where(DocumentField.field_spec_id == ancienne.id)))
        .scalars()
        .all()
    )
    for df in anciens:
        statuts = (
            (
                await db.execute(
                    select(DocumentField).where(
                        DocumentField.document_id == df.document_id,
                        DocumentField.field_spec_id.in_(list(ids_statut)),
                    )
                )
            )
            .scalars()
            .all()
        )
        par_statut = {ids_statut[s.field_spec_id]: s for s in statuts}
        existants = {
            r.field_spec_id
            for r in (
                await db.execute(
                    select(DocumentField.field_spec_id).where(
                        DocumentField.document_id == df.document_id,
                        DocumentField.field_spec_id.in_([s.id for s in nouvelles.values()]),
                    )
                )
            ).all()
        }
        cible_ocr, _ = cible_date(ordre, {k: v.ocr_value for k, v in par_statut.items()})
        cible_vraie, n = cible_date(ordre, {k: v.resolved_value for k, v in par_statut.items()})
        if n > 1 and df.resolved_value:
            cochees = [s for s in ordre if s in par_statut and _coche(par_statut[s].resolved_value)]
            a_revoir.append(f"  document {df.document_id} : {', '.join(cochees)}")
        lignes: Dict[str, Any] = {}
        for statut, spec in nouvelles.items():
            if spec.id in existants:
                continue
            ligne = DocumentField(
                document_id=df.document_id,
                field_spec_id=spec.id,
                group_id=None,
                ocr_value=df.ocr_value if statut == cible_ocr else None,
                resolved_value=df.resolved_value if statut == cible_vraie else None,
                status=df.status,
                resolved_by=df.resolved_by if statut == cible_vraie else None,
            )
            db.add(ligne)
            lignes[statut] = ligne
            compte["champs de document crees"] += 1
            if statut == cible_vraie and df.resolved_value:
                compte["dates deplacees"] += 1
        await db.flush()

        # Propositions : un job qui avait verifie l'ancienne date verifie
        # toutes les nouvelles, la date allant a la case que ce job a cochee.
        propositions = (
            (
                await db.execute(
                    select(FieldProposal)
                    .where(FieldProposal.document_field_id == df.id)
                    .order_by(FieldProposal.created_at, FieldProposal.id)
                )
            )
            .scalars()
            .all()
        )
        derniere: Dict[int, Any] = {}
        for p in propositions:
            derniere[p.job_id] = p
        for job_id, p in derniere.items():
            coches = {}
            for statut, ligne_statut in par_statut.items():
                vue = (
                    await db.execute(
                        select(FieldProposal.value)
                        .where(
                            FieldProposal.document_field_id == ligne_statut.id,
                            FieldProposal.job_id == job_id,
                        )
                        .order_by(FieldProposal.created_at.desc(), FieldProposal.id.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                coches[statut] = vue if vue is not None else ligne_statut.resolved_value
            cible_job, _ = cible_date(ordre, coches)
            for statut, ligne in lignes.items():
                db.add(
                    FieldProposal(
                        document_field_id=ligne.id,
                        job_id=job_id,
                        step=p.step,
                        value_type=p.value_type,
                        value=p.value if statut == cible_job else None,
                    )
                )
                compte["propositions creees"] += 1
        await db.flush()
        for table, colonne in (
            (FieldProposal, FieldProposal.document_field_id),
            (DocumentField, DocumentField.id),
        ):
            await db.execute(
                delete(table).where(colonne == df.id).execution_options(synchronize_session=False)
            )
        db.expunge(df)


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