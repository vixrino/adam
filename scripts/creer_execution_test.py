"""
scripts/creer_execution_test.py
-------------------------------
Cree une recette de test figee et une execution en attente, que le worker de
benchmark (TestExecutionWorker) prend au cycle suivant. Provisoire : le CLI
Runner fera ce travail proprement.

Une recette designe des documents dont la verite terrain a ete etablie par des
humains. Par defaut, ce sont les documents du dataset dont au moins un champ
porte une proposition humaine (field_proposal) : les autres n'apporteraient
aucun champ au denominateur.

Le paquet *_core (nota_core ou adam_core) est trouve sous src/ : le script
tourne tel quel dans les deux depots, depuis la racine du depot (.env).

Usage :
    python scripts/creer_execution_test.py --dataset-id 4
    python scripts/creer_execution_test.py --dataset-id 4 --documents 12 15 18
    python scripts/creer_execution_test.py --recipe-id 2        # relancer une recette
    python scripts/creer_execution_test.py --dataset-id 4 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def _paquets() -> tuple[str, str]:
    """(paquet *_core, paquet *_api) presents sous src/."""
    cores = sorted(p.name for p in SRC.glob("*_core") if (p / "models").is_dir())
    apis = sorted(p.name for p in SRC.glob("*_api") if (p / "core" / "config.py").is_file())
    if len(cores) != 1 or len(apis) != 1:
        raise SystemExit(f"attendu un *_core et un *_api sous src/, trouve {cores} {apis}")
    return cores[0], apis[0]


async def creer(
    dataset_id: Optional[int],
    documents: List[int],
    recipe_id: Optional[int],
    nom: Optional[str],
    matricule: Optional[str],
    dry_run: bool,
) -> None:
    core, api = _paquets()
    from sqlalchemy import func, select

    modeles = importlib.import_module(f"{core}.models")
    statuts = importlib.import_module(f"{core}.enums.status")
    session_mod = importlib.import_module(f"{core}.db.session")
    settings = importlib.import_module(f"{api}.core.config").settings
    core_settings = importlib.import_module(f"{core}.core.config").get_core_settings()
    session_mod.init_engine(core_settings.async_database_url)

    Dataset, Document, DocumentField, FieldProposal, TestExecution, TestRecipe, User = (
        getattr(modeles, n)
        for n in (
            "Dataset",
            "Document",
            "DocumentField",
            "FieldProposal",
            "TestExecution",
            "TestRecipe",
            "User",
        )
    )

    matricule = (matricule or settings.api_dev_matricule).upper()
    async with session_mod.get_async_session() as db:
        createur: Any = (
            await db.execute(select(User.id).where(func.upper(User.matricule) == matricule))
        ).scalar_one_or_none()
        if createur is None:
            raise SystemExit(f"matricule {matricule} inconnu de la table user (--matricule)")

        if recipe_id is not None:
            recette = await db.get(TestRecipe, recipe_id)
            if recette is None:
                raise SystemExit(f"recette {recipe_id} introuvable")
            if recette.status != statuts.TestRecipeStatus.LOCKED.value:
                raise SystemExit(f"recette {recipe_id} non verrouillee ({recette.status})")
            dataset = await db.get(Dataset, recette.dataset_id)
            print(f" recette existante id={recette.id} : {len(recette.document_ids)} document(s)")
        else:
            if dataset_id is None:
                raise SystemExit("--dataset-id ou --recipe-id requis")
            dataset = await db.get(Dataset, dataset_id)
            if dataset is None:
                raise SystemExit(f"dataset {dataset_id} introuvable")
            if not documents:
                verifies = (
                    select(DocumentField.document_id)
                    .join(FieldProposal, FieldProposal.document_field_id == DocumentField.id)
                    .distinct()
                )
                documents = list(
                    (
                        await db.execute(
                            select(Document.id)
                            .where(Document.dataset_id == dataset_id)
                            .where(Document.id.in_(verifies))
                            .order_by(Document.id)
                        )
                    )
                    .scalars()
                    .all()
                )
            if not documents:
                raise SystemExit(
                    f"dataset {dataset_id} : aucun document avec une proposition humaine. "
                    "Sans verite terrain, il n'y a rien a mesurer (--documents pour forcer)."
                )
            maintenant = datetime.now(timezone.utc)
            recette = TestRecipe(
                dataset_id=dataset_id,
                name=nom or f"recette {maintenant:%Y-%m-%d %H:%M}",
                document_ids=documents,
                status=statuts.TestRecipeStatus.LOCKED.value,
                locked_at=maintenant,
                created_by_user_id=createur,
            )
            print(f" recette : {recette.name} — documents {documents}")
            if not dry_run:
                db.add(recette)
                await db.flush()

        execution = TestExecution(
            recipe_id=recette.id,
            status=statuts.TestExecutionStatus.PENDING.value,
            # Provisoire : le worker y recopie le moteur reellement utilise.
            ocr_provider=dataset.ocr_provider,
            ocr_model_id=dataset.ocr_model_id,
            created_by_user_id=createur,
        )
        if dry_run:
            print(" (dry-run) rien n'est ecrit")
            await db.rollback()
            return
        db.add(execution)
        await db.flush()
        print(f" execution id={execution.id} creee en PENDING : le worker la prendra")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("Usage")[0])
    parser.add_argument("--dataset-id", type=int)
    parser.add_argument("--documents", type=int, nargs="*", default=[])
    parser.add_argument("--recipe-id", type=int, help="Relancer une recette deja figee")
    parser.add_argument("--nom", help="Nom de la recette")
    parser.add_argument("--matricule", help="Createur (defaut : API_DEV_MATRICULE)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        creer(
            args.dataset_id, args.documents, args.recipe_id, args.nom, args.matricule, args.dry_run
        )
    )


if __name__ == "__main__":
    main()
