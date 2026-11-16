"""
scripts/lancer_benchmark.py
---------------------------
Lance un banc d'essai OCR de bout en bout, en une commande :

0. prepare la base : ignore un POSTGRES_DB reste pose dans le terminal (la
   base est celle du .env), verifie que les tables du benchmark ont toutes
   leurs colonnes et, sinon, applique les migrations (alembic upgrade heads) ;
1. choisit le dataset (celui qui a le plus de documents a verite humaine, ou
   --dataset-id) ;
2. fige ses documents verifies dans un export, cree la recette et l'execution
   (meme code que creer_execution_test.py) ;
3. execute la recette ici meme avec le worker de benchmark : pas besoin d'un
   worker lance a cote (s'il en tourne un, il peut la prendre, le script
   attend alors la fin) ;
4. affiche le resultat (score, taux, fourchettes, verdict, avertissements) ;
5. ecrit le rapport PDF, comme la route /test-executions/{id}/metriques.pdf.

Les appels OCR sont reels si OCR_MOCK_ENABLED=false : ils coutent. --dry-run
montre ce qui serait lance sans rien ecrire ni appeler.

Le paquet *_core est trouve sous src/ : le script tourne tel quel dans adam et
dans nota, depuis la racine du depot (.env).

Usage :
    python scripts/lancer_benchmark.py
    python scripts/lancer_benchmark.py --dataset-id 4
    python scripts/lancer_benchmark.py --dataset-id 4 --documents 12 15
    python scripts/lancer_benchmark.py --recipe-id 2          # rejouer une recette
    python scripts/lancer_benchmark.py --dry-run
    python scripts/lancer_benchmark.py --execution-id 1      # reprendre une execution
    python scripts/lancer_benchmark.py --sans-migration   # ne jamais migrer
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import importlib.util
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, List, Optional

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

TERMINES = ("COMPLETED", "FAILED")


def _prefixe() -> str:
    """'adam' ou 'nota', d'apres le paquet *_core present sous src/."""
    cores = sorted(p.name for p in SRC.glob("*_core") if (p / "models").is_dir())
    if len(cores) != 1:
        raise SystemExit(f"attendu un *_core sous src/, trouve {cores}")
    return cores[0].removesuffix("_core")


def _module(nom: str) -> Any:
    return importlib.import_module(f"{_prefixe()}_{nom}")


def _script_voisin(nom: str) -> Any:
    """Charge un autre script de scripts/ (pas un paquet importable)."""
    spec = importlib.util.spec_from_file_location(nom, Path(__file__).with_name(f"{nom}.py"))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _pct(valeur: Any) -> str:
    return "-" if valeur is None else f"{float(valeur) * 100:.1f} %"


# -- 0. Base a jour -----------------------------------------------------------

#: Tables que le benchmark lit ou ecrit : une colonne du modele absente de la
#: base veut dire une migration non appliquee.
TABLES_BENCHMARK = (
    "DatasetExport",
    "TestRecipe",
    "TestExecution",
    "ComparisonResult",
    "EvaluationReport",
)


async def _colonnes_manquantes() -> List[str]:
    """Colonnes des modeles du benchmark absentes de la base ("table.colonne")."""
    from sqlalchemy import text

    m = _module("core.models")
    session_mod = _module("core.db.session")
    manquantes: List[str] = []
    async with session_mod.get_async_session() as db:
        for nom in TABLES_BENCHMARK:
            table = getattr(m, nom).__table__
            schema = table.schema or (await db.execute(text("SELECT current_schema()"))).scalar()
            presentes = set(
                (
                    await db.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = :schema AND table_name = :table"
                        ),
                        {"schema": schema, "table": table.name},
                    )
                )
                .scalars()
                .all()
            )
            if not presentes:
                manquantes.append(f"{table.name} (table absente)")
                continue
            manquantes += [
                f"{table.name}.{c.name}" for c in table.columns if c.name not in presentes
            ]
    return manquantes


def _migrer() -> None:
    """alembic upgrade heads, depuis la racine du depot (.env)."""
    ini = SRC / f"{_prefixe()}_core" / "alembic.ini"
    commande = [sys.executable, "-m", "alembic", "-c", str(ini), "upgrade", "heads"]
    print(f"Migrations : {' '.join(commande[1:])}")
    resultat = subprocess.run(
        commande, cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True, check=False
    )
    lignes = (resultat.stdout + resultat.stderr).strip().splitlines()
    for ligne in lignes:
        if "Running upgrade" in ligne:
            print(f"  {ligne.strip()}")
    if resultat.returncode != 0:
        print("\n".join(f"  {ligne}" for ligne in lignes[-15:]))
        raise SystemExit(
            "Echec des migrations : rien n'a ete lance. Collez la sortie ci-dessus, avec "
            f"celle de : uv run --all-extras alembic -c {ini.relative_to(ROOT)} heads"
        )


async def _verifier_base(migrer: bool, dry_run: bool) -> None:
    manquantes = await _colonnes_manquantes()
    if not manquantes:
        print("Base a jour pour le benchmark.\n")
        return
    print(f"Base en retard sur le code : {len(manquantes)} colonne(s) manquante(s)")
    for colonne in manquantes[:10]:
        print(f"  - {colonne}")
    if dry_run:
        print("(dry-run) les migrations seraient appliquees au vrai lancement : arret ici.")
        raise SystemExit(0)
    if not migrer:
        raise SystemExit("--sans-migration : appliquez les migrations, puis relancez.")
    # alembic ouvre sa propre boucle asyncio : il tourne dans un processus a part.
    await asyncio.to_thread(_migrer)
    restantes = await _colonnes_manquantes()
    if restantes:
        raise SystemExit(
            "Migrations appliquees, mais il manque encore : "
            + ", ".join(restantes[:10])
            + ". La migration correspondante n'est pas dans ce depot."
        )
    print("Base migree et a jour.\n")


# -- 1. Choix du dataset ------------------------------------------------------


async def _choisir_dataset() -> int:
    """Le dataset qui a le plus de documents a verite humaine."""
    from sqlalchemy import distinct, func, select

    m = _module("core.models")
    session_mod = _module("core.db.session")
    async with session_mod.get_async_session() as db:
        lignes = (
            await db.execute(
                select(m.Document.dataset_id, m.Dataset.name, func.count(distinct(m.Document.id)))
                .join(m.Dataset, m.Dataset.id == m.Document.dataset_id)
                .join(m.DocumentField, m.DocumentField.document_id == m.Document.id)
                .join(m.FieldProposal, m.FieldProposal.document_field_id == m.DocumentField.id)
                .group_by(m.Document.dataset_id, m.Dataset.name)
                .order_by(func.count(distinct(m.Document.id)).desc(), m.Document.dataset_id)
            )
        ).all()
    if not lignes:
        raise SystemExit(
            "Aucun document avec une verite humaine : validez au moins un champ d'un "
            "document dans l'IHM, puis relancez."
        )
    print("Datasets mesurables :")
    for dataset_id, nom, n in lignes:
        print(f"  dataset_id={dataset_id:<4} {nom}  {n} document(s) verifie(s)")
    choisi = lignes[0][0]
    print(f"-> dataset {choisi} retenu (--dataset-id pour en choisir un autre)\n")
    return int(choisi)


# -- 3. Execution -------------------------------------------------------------


async def _statut(execution_id: int) -> tuple[str, int, int, Optional[str]]:
    from sqlalchemy import select

    m = _module("core.models")
    session_mod = _module("core.db.session")
    E = m.TestExecution
    # documents_traites vient du ticket progression : un depot qui ne l'a pas
    # encore suit les documents compares.
    traites = getattr(E, "documents_traites", None) or E.documents_compared
    async with session_mod.get_async_session() as db:
        ligne = (
            await db.execute(
                select(E.status, traites.label("traites"), E.recipe_id, E.error_message).where(
                    E.id == execution_id
                )
            )
        ).one()
        recette = await db.get(m.TestRecipe, ligne.recipe_id)
    total = len(recette.document_ids or []) if recette else 0
    return str(ligne.status), int(ligne.traites or 0), total, ligne.error_message


async def _anterieures_en_attente(execution_id: int) -> List[int]:
    from sqlalchemy import select

    m = _module("core.models")
    session_mod = _module("core.db.session")
    async with session_mod.get_async_session() as db:
        return list(
            (
                await db.execute(
                    select(m.TestExecution.id)
                    .where(m.TestExecution.status == "PENDING")
                    .where(m.TestExecution.id < execution_id)
                    .order_by(m.TestExecution.id)
                )
            )
            .scalars()
            .all()
        )


async def _executer(execution_id: int) -> str:
    worker_mod = _module("worker.benchmark.worker")
    worker = worker_mod.TestExecutionWorker()
    avant = await _anterieures_en_attente(execution_id)
    if avant:
        print(
            f"Attention : executions plus anciennes en attente {avant}. Le worker les "
            "prend d'abord (ordre d'arrivee).\n"
        )
    debut = time.monotonic()
    dernier = None
    while True:
        statut, traites, total, message = await _statut(execution_id)
        if statut in TERMINES:
            duree = time.monotonic() - debut
            print(f"\nExecution {execution_id} : {statut} en {duree:.0f} s")
            if message:
                print(f"  constats : {message}")
            return statut
        if statut == "PENDING":
            # Un cycle complet : reserve la plus ancienne execution en attente
            # et la traite jusqu'au bout.
            print(f"Execution {execution_id} : traitement en cours ({total} document(s))...")
            await worker.poll()
        else:
            # RUNNING chez un autre worker : on suit sa progression.
            if (traites, total) != dernier:
                print(f"  {traites}/{total} document(s) traite(s) par un autre worker")
                dernier = (traites, total)
            await asyncio.sleep(10)


# -- 4. et 5. Resultat et PDF -------------------------------------------------


async def _resultat(execution_id: int, sortie: Path) -> None:
    router = _module("api.routers.benchmark")
    session_mod = _module("core.db.session")
    # Les filtres et le PDF sont venus apres les metriques : un depot plus
    # ancien a les metriques sans eux, le resultat s'affiche quand meme.
    classe_filtres = getattr(_module("core.benchmark.metriques"), "FiltresChamps", None)
    filtres = classe_filtres() if classe_filtres else None
    pdf = None
    async with session_mod.get_async_session() as db:
        if filtres is not None:
            metriques = await router._metriques(  # pylint: disable=protected-access
                db, execution_id, False, filtres
            )
        else:
            metriques = await router._metriques(  # pylint: disable=protected-access
                db, execution_id, False
            )
        if hasattr(router, "metriques_pdf") and filtres is not None:
            try:
                pdf = await router.metriques_pdf(execution_id, filtres, None, db)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                print(f"(PDF non genere : {type(exc).__name__}: {exc})")

    g = metriques["global"]
    print("\nRESULTAT")
    print(f"  valeurs jugees      : {g['valeurs_jugees']}")
    print(
        f"  justes {g['justes']}, fausses {g['fausses']}, manquees {g['manquees']}, "
        f"inventees {g['inventees']}"
    )
    print(f"  score (F1)          : {_pct(g['score'])}")
    fl = g.get("fourchette_lectures_justes") or [None, None]
    fv = g.get("fourchette_valeurs_trouvees") or [None, None]
    print(
        f"  lectures justes     : {_pct(g['taux_lectures_justes'])}  "
        f"(95 % : {_pct(fl[0])} a {_pct(fl[1])})"
    )
    print(
        f"  valeurs trouvees    : {_pct(g['taux_valeurs_trouvees'])}  "
        f"(95 % : {_pct(fv[0])} a {_pct(fv[1])})"
    )
    print(f"  erreur caracteres   : {_pct(g.get('taux_erreur_caracteres'))}")
    cout = metriques.get("cout") or {}
    print(
        f"  appels OCR          : {cout.get('appels_ocr')} "
        f"({cout.get('appels_par_document')} par document)"
    )
    verdict = metriques.get("verdict") or {}
    if verdict.get("reussi") is not None:
        print(f"  verdict             : {'REUSSI' if verdict['reussi'] else 'ECHEC'}")
    pires = sorted(metriques.get("par_champ") or [], key=lambda c: c.get("reussite") or 0)[:5]
    if pires:
        print("  champs les plus en erreur :")
        for champ in pires:
            print(f"    {champ['champ']}  reussite {_pct(champ.get('reussite'))}")
    for avertissement in metriques.get("avertissements") or []:
        print(f"  ! {avertissement}")

    if pdf is None:
        print("\nPas de rapport PDF dans ce depot : resultat affiche ci-dessus seulement.")
        return
    sortie.write_bytes(pdf.body)
    print(f"\nPDF ecrit : {sortie.resolve()}")


# -- Orchestration ------------------------------------------------------------


async def lancer(args: argparse.Namespace) -> None:
    api_settings = _module("api.core.config").settings
    base = _module("core.core.config").get_core_settings().postgres_db
    print(
        f"Base : {base} | moteur OCR : {'MOCK' if api_settings.ocr_mock_enabled else 'reel (appels payants)'}\n"
    )
    if not api_settings.comparison_hmac_key:
        raise SystemExit("COMPARISON_HMAC_KEY absente du .env : l'execution echouerait.")
    await _verifier_base(migrer=not args.sans_migration, dry_run=args.dry_run)

    execution_id = args.execution_id
    if execution_id is None and not args.nouvelle and not args.dry_run:
        # Un lancement precedent interrompu laisse son execution en PENDING :
        # la reprendre, plutot que d'en creer une autre et payer l'OCR deux fois.
        en_attente = await _anterieures_en_attente(2**31 - 1)
        if en_attente:
            execution_id = en_attente[-1]
            print(
                f"Execution {execution_id} deja en attente : reprise "
                "(--nouvelle pour en creer une autre)\n"
            )
    if execution_id is None:
        dataset_id = args.dataset_id
        if dataset_id is None and args.recipe_id is None:
            dataset_id = await _choisir_dataset()

        creation = _script_voisin("creer_execution_test")
        execution_id = await creation.creer(
            dataset_id, args.documents, args.recipe_id, args.nom, args.matricule, args.dry_run
        )
        if execution_id is None:
            return

    statut = await _executer(execution_id)
    if statut != "COMPLETED":
        raise SystemExit(1)
    await _resultat(execution_id, args.sortie or Path(f"rapport_test_{execution_id}.pdf"))


def main() -> None:
    """Point d'entree en ligne de commande."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dataset-id", type=int, help="Defaut : le plus de documents verifies")
    parser.add_argument("--documents", type=int, nargs="*", default=[])
    parser.add_argument("--recipe-id", type=int, help="Rejouer une recette deja figee")
    parser.add_argument("--nom", help="Nom de la recette")
    parser.add_argument("--matricule", help="Createur (defaut : API_DEV_MATRICULE)")
    parser.add_argument("--execution-id", type=int, help="Reprendre cette execution")
    parser.add_argument(
        "--nouvelle", action="store_true", help="Ne pas reprendre une execution en attente"
    )
    parser.add_argument("--sortie", type=Path, help="PDF (defaut rapport_test_<id>.pdf)")
    parser.add_argument("--dry-run", action="store_true", help="Rien n'est ecrit ni migre")
    parser.add_argument("--sans-migration", action="store_true", help="Ne jamais migrer")
    parser.add_argument(
        "--garder-postgres-db",
        action="store_true",
        help="Utiliser POSTGRES_DB du terminal au lieu de celui du .env",
    )
    args = parser.parse_args()

    # Les variables d'environnement priment sur le .env : un POSTGRES_DB reste
    # pose apres une demo ferait viser (et migrer) la base de demo.
    if os.environ.get("POSTGRES_DB") and not args.garder_postgres_db:
        print(
            f"POSTGRES_DB={os.environ.pop('POSTGRES_DB')} du terminal ignore : base du .env "
            "(--garder-postgres-db pour le garder)"
        )

    core = _module("core.core.config").get_core_settings()
    try:
        _module("core.utils.logging").setup_logging(core)
    except (ValueError, ImportError):
        # Formateur json absent du venv : les logs du worker restent lisibles.
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _module("core.db.session").init_engine(core.async_database_url, echo=False)
    asyncio.run(lancer(args))


if __name__ == "__main__":
    main()
