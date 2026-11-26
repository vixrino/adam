"""
scripts/lister_ids_benchmark.py
-------------------------------
Liste les identifiants dont un benchmark a besoin : datasets, documents dont
au moins un champ porte une proposition humaine (les seuls qu'une recette
peut mesurer), recettes et executions. Il precede creer_execution_test.py et
la lecture des metriques, qui demandent ces ids.

Rien n'est ecrit en base. Seuls des identifiants, des statuts et des comptes
sont affiches : ni valeur de champ ni nom de fichier, qui peuvent porter des
donnees personnelles.

Le paquet *_core est trouve sous src/ : le script tourne tel quel dans les deux
depots, depuis la racine du depot (.env).

Usage :
    python scripts/lister_ids_benchmark.py
    python scripts/lister_ids_benchmark.py --dataset-id 9
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def _paquet_core() -> str:
    """Le paquet *_core present sous src/."""
    cores = sorted(p.name for p in SRC.glob("*_core") if (p / "models").is_dir())
    if len(cores) != 1:
        raise SystemExit(f"attendu un *_core sous src/, trouve {cores}")
    return cores[0]


def _date(valeur: Any) -> str:
    return valeur.strftime("%Y-%m-%d %H:%M") if valeur else "-"


async def lister(dataset_id: Optional[int]) -> None:
    """Affiche datasets, documents verifies, recettes et executions."""
    core = _paquet_core()
    from sqlalchemy import distinct, func, select

    modeles = importlib.import_module(f"{core}.models")
    session_mod = importlib.import_module(f"{core}.db.session")
    settings = importlib.import_module(f"{core}.core.config").get_core_settings()
    session_mod.init_engine(settings.async_database_url)
    Dataset, Document, DocumentField, FieldProposal, TestExecution, TestRecipe = (
        getattr(modeles, n)
        for n in (
            "Dataset",
            "Document",
            "DocumentField",
            "FieldProposal",
            "TestExecution",
            "TestRecipe",
        )
    )

    async with session_mod.get_async_session() as db:
        # Colonnes nommees, pas d'entites : une colonne du modele absente de la
        # base (adam et nota divergent) ne fait pas echouer la liste.
        requete_datasets = select(Dataset.id, Dataset.name, Dataset.status).order_by(Dataset.id)
        if dataset_id is not None:
            requete_datasets = requete_datasets.where(Dataset.id == dataset_id)
        datasets = (await db.execute(requete_datasets)).all()
        ids_datasets = [d.id for d in datasets]

        documents = dict(
            (
                await db.execute(
                    select(Document.dataset_id, func.count(Document.id))
                    .where(Document.dataset_id.in_(ids_datasets))
                    .group_by(Document.dataset_id)
                )
            ).all()
        )
        # Champs a proposition humaine, par document : le denominateur d'une mesure.
        verifies = (
            await db.execute(
                select(
                    Document.dataset_id,
                    Document.id,
                    Document.status,
                    func.count(distinct(DocumentField.id)),
                )
                .join(DocumentField, DocumentField.document_id == Document.id)
                .join(FieldProposal, FieldProposal.document_field_id == DocumentField.id)
                .where(Document.dataset_id.in_(ids_datasets))
                .group_by(Document.dataset_id, Document.id, Document.status)
                .order_by(Document.dataset_id, Document.id)
            )
        ).all()
        recettes = (
            await db.execute(
                select(
                    TestRecipe.id,
                    TestRecipe.dataset_id,
                    TestRecipe.name,
                    TestRecipe.status,
                    TestRecipe.locked_at,
                    TestRecipe.document_ids,
                )
                .where(TestRecipe.dataset_id.in_(ids_datasets))
                .order_by(TestRecipe.id)
            )
        ).all()
        executions = (
            await db.execute(
                select(
                    TestExecution.id,
                    TestExecution.recipe_id,
                    TestExecution.status,
                    TestExecution.finished_at,
                    TestExecution.fields_compared,
                )
                .where(TestExecution.recipe_id.in_([r.id for r in recettes]))
                .order_by(TestExecution.id)
            )
        ).all()

    print("\nDATASETS")
    if not datasets:
        print("  aucun")
    for d in datasets:
        n_verifies = sum(1 for v in verifies if v[0] == d.id)
        print(
            f"  dataset_id={d.id:<4} {d.name}  [{d.status}]  "
            f"{documents.get(d.id, 0)} document(s), {n_verifies} avec verite humaine"
        )

    print("\nDOCUMENTS AVEC VERITE HUMAINE (mesurables)")
    if not verifies:
        print("  aucun : validez au moins un champ d'un document dans l'IHM")
    for ds_id, doc_id, statut, n_champs in verifies:
        print(
            f"  dataset_id={ds_id:<4} document_id={doc_id:<6} [{statut}]  "
            f"{n_champs} champ(s) verifie(s)"
        )

    print("\nRECETTES")
    if not recettes:
        print("  aucune")
    for r in recettes:
        verrou = "verrouillee" if r.locked_at else "non verrouillee"
        print(
            f"  recipe_id={r.id:<4} dataset_id={r.dataset_id:<4} {r.name}  [{r.status}, {verrou}]  "
            f"{len(r.document_ids or [])} document(s)"
        )

    print("\nEXECUTIONS")
    if not executions:
        print("  aucune")
    for e in executions:
        print(
            f"  execution_id={e.id:<4} recipe_id={e.recipe_id:<4} [{e.status}]  "
            f"fin {_date(e.finished_at)}  {e.fields_compared or 0} champ(s) compare(s)"
        )

    termines = [e for e in executions if str(e.status).endswith("COMPLETED")]
    en_cours = [e for e in executions if str(e.status).endswith(("PENDING", "RUNNING"))]
    print("\nENSUITE")
    if en_cours:
        print(
            f"  execution_id={en_cours[-1].id} en {en_cours[-1].status} : laisser tourner le "
            "worker (python -m <paquet>_worker.main) jusqu'a COMPLETED, puis relancer ce script"
        )
    elif termines:
        print(
            f"  metriques : GET /api/v1/test-executions/{termines[-1].id}/metriques "
            "dans /docs, tous_les_champs=true"
        )
    elif verifies:
        ds_id, doc_id = verifies[0][0], verifies[0][1]
        print(
            "  creer une execution : python scripts/creer_execution_test.py "
            f"--dataset-id {ds_id} --documents {doc_id}"
        )
    else:
        print("  aucun document mesurable : il faut d'abord une verite humaine")


def main() -> None:
    """Point d'entree en ligne de commande."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dataset-id", type=int, help="Limiter a ce dataset")
    args = parser.parse_args()
    asyncio.run(lister(args.dataset_id))


if __name__ == "__main__":
    main()
