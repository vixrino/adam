"""
scripts/demo_metriques.py
-------------------------
Fait tourner le benchmark de bout en bout et ecrit le JSON des metriques, sans
document reel ni appel OCR : pour verifier la chaine, pas pour mesurer un moteur.

Etapes :
  1. recree une base a part, <POSTGRES_DB>_demo_metriques : seed.py --reset vide
     toutes les tables, et ne doit jamais tourner sur la base de travail ;
  2. y joue seed.py --reset --fake-ocr (un dossier CERFA fictif) ;
  3. pose une verite humaine sur des champs texte, avec des cas de chaque sorte
     (justes, fausses, manquees, inventees, vides) pour que le score ne soit
     ni 0 ni 1 ;
  4. cree recette et execution avec creer_execution_test.py ;
  5. passe une fois le vrai worker de benchmark, avec le connecteur mock et des
     images de page factices dans un dossier temporaire ;
  6. ecrit les metriques, du meme calcul que GET /test-executions/{id}/metriques.

La base de travail n'est jamais ouverte en ecriture. Les valeurs sont fictives ;
seuls des identifiants et des comptes sont affiches.

Le paquet *_core est trouve sous src/ : le script tourne tel quel dans les deux
depots, depuis la racine du depot (.env).

Usage :
    python scripts/demo_metriques.py
    python scripts/demo_metriques.py --sortie metriques_demo.json --champs 60
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

SUFFIXE_BASE = "_demo_metriques"
#: Commentaire pose sur la base de demo a sa creation : seule une base qui le
#: porte peut etre supprimee et recreee par la demo.
MARQUE_DEMO = "base de demo creee par scripts/demo_metriques.py"
#: Lecture que le connecteur mock rend pour chaque cle detectee.
VALEUR_LUE = "valeur-mock"
#: Repartition des cas sur dix champs : 6 justes, 1 fausse, 1 manquee,
#: 1 inventee, 1 vide. (lue par le moteur, verite humaine)
CAS = [
    (True, VALEUR_LUE),
    (True, VALEUR_LUE),
    (True, VALEUR_LUE),
    (True, VALEUR_LUE),
    (True, VALEUR_LUE),
    (True, VALEUR_LUE),
    (True, "autre valeur"),
    (False, "valeur attendue"),
    (True, None),
    (False, None),
]


def _prefixe() -> str:
    """'adam' ou 'nota', d'apres le paquet *_core present sous src/."""
    cores = sorted(p.name for p in SRC.glob("*_core") if (p / "models").is_dir())
    if len(cores) != 1:
        raise SystemExit(f"attendu un *_core sous src/, trouve {cores}")
    return cores[0].removesuffix("_core")


def repartir(champs: List[Tuple[int, str]]) -> Tuple[List[str], Dict[int, Any]]:
    """Cles que le moteur lira et verite par document_field, selon CAS.

    `champs` : (document_field_id, cle d'appel) des champs retenus.
    """
    detectees: List[str] = []
    verite: Dict[int, Any] = {}
    for rang, (df_id, cle) in enumerate(champs):
        lue, attendue = CAS[rang % len(CAS)]
        if lue:
            detectees.append(cle)
        verite[df_id] = attendue
    return detectees, verite


async def _creer_base(nom: str) -> None:
    import asyncpg

    core = importlib.import_module(f"{_prefixe()}_core.core.config").get_core_settings()
    conn = await asyncpg.connect(
        user=core.postgres_user,
        password=core.postgres_password,
        host=core.postgres_host,
        port=core.postgres_port,
        database="postgres",
    )
    try:
        # Recreee a chaque demo : create_all ne fait que creer les tables
        # absentes, et une base de demo d'une version precedente garderait ses
        # anciennes colonnes. Ne supprime qu'une base que la demo a elle-meme
        # creee et marquee (commentaire MARQUE_DEMO) : jamais une base de
        # travail, meme si son nom finissait par le suffixe.
        marque = await conn.fetchval(
            "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = $1",
            nom,
        )
        existe = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", nom)
        if existe and marque != MARQUE_DEMO:
            raise SystemExit(
                f"refus de supprimer {nom} : elle n'a pas ete creee par cette demo "
                "(la supprimer a la main si c'est bien une base de demo)"
            )
        if existe:
            # Sans WITH (FORCE), absent avant Postgres 13 : couper d'abord les
            # sessions encore ouvertes sur la base de demo.
            await conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid()",
                nom,
            )
            await conn.execute(f'DROP DATABASE "{nom}"')
        await conn.execute(f'CREATE DATABASE "{nom}"')
        await conn.execute(f"COMMENT ON DATABASE \"{nom}\" IS '{MARQUE_DEMO}'")
    finally:
        await conn.close()


def _lancer(script: str, *args: str) -> str:
    """Lance un script du depot sur la base de demo ; rend sa sortie."""
    resultat = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    if resultat.returncode != 0:
        print(resultat.stdout[-2000:], resultat.stderr[-2000:], sep="\n")
        raise SystemExit(f"{script} a echoue (code {resultat.returncode})")
    return resultat.stdout


async def _poser_verite(nb_champs: int) -> Tuple[int, int, int, List[str]]:
    """Verite humaine sur des champs texte du document seede.

    Rend (dataset_id, document_id, file_id, cles detectees).
    """
    from sqlalchemy import select

    p = _prefixe()
    modeles = importlib.import_module(f"{p}_core.models")
    statuts = importlib.import_module(f"{p}_core.enums.status")
    session_mod = importlib.import_module(f"{p}_core.db.session")

    async with session_mod.get_async_session() as db:
        document = (await db.execute(select(modeles.Document).limit(1))).scalar_one()
        lignes = (
            await db.execute(
                select(
                    modeles.DocumentField.id,
                    modeles.FieldSpec.section_id,
                    modeles.FieldSpec.field_key,
                )
                .join(
                    modeles.FieldSpec, modeles.FieldSpec.id == modeles.DocumentField.field_spec_id
                )
                .where(modeles.DocumentField.document_id == document.id)
                .where(modeles.DocumentField.group_id.is_(None))
                .where(modeles.FieldSpec.value_type == statuts.FieldValueType.TEXT.value)
                .order_by(modeles.FieldSpec.page, modeles.FieldSpec.display_order)
                .limit(nb_champs)
            )
        ).all()
        if not lignes:
            raise SystemExit("aucun champ texte dans le document seede")
        detectees, verite = repartir([(i, f"{s}.{k}") for i, s, k in lignes])

        agent_id = (await db.execute(select(modeles.User.id).limit(1))).scalar_one()
        job = modeles.Job(
            dataset_id=document.dataset_id,
            document_id=document.id,
            agent_id=agent_id,
            state=statuts.JobState.SUBMITTED.value,
            step=statuts.JobStep.VALIDATION.value,
        )
        db.add(job)
        await db.flush()
        for df_id, attendue in verite.items():
            champ = await db.get(modeles.DocumentField, df_id)
            champ.resolved_value = attendue
            db.add(
                modeles.FieldProposal(
                    document_field_id=df_id,
                    job_id=job.id,
                    step=statuts.JobStep.VALIDATION.value,
                    value_type=statuts.FieldValueType.TEXT.value,
                    value=attendue,
                )
            )
        await db.commit()
        return document.dataset_id, document.id, document.file_id, detectees


async def _benchmark(file_id: int, detectees: List[str], pvc: Path) -> None:
    """Un passage du vrai worker, moteur mock, images factices."""
    p = _prefixe()
    worker_mod = importlib.import_module(f"{p}_worker.benchmark.worker")
    mock = importlib.import_module(f"{p}_worker.connectors.mock")
    poller = importlib.import_module(f"{p}_worker.prepopulation.poller")

    pages = pvc / poller.default_pages_dir(file_id)
    pages.mkdir(parents=True, exist_ok=True)
    (pages / "page_001.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    worker = worker_mod.TestExecutionWorker(
        connector=mock.MockOcrConnector(detectees, value=VALEUR_LUE),
        pvc_root=pvc,
        cle_hmac="demo-metriques",
    )
    await worker.poll()


async def _metriques(execution_id: int) -> Dict[str, Any]:
    p = _prefixe()
    router = importlib.import_module(f"{p}_api.routers.benchmark")
    session_mod = importlib.import_module(f"{p}_core.db.session")
    async with session_mod.get_async_session() as db:
        return await router._metriques(db, execution_id, True)


async def _derniere_execution() -> Tuple[int, str]:
    from sqlalchemy import select

    p = _prefixe()
    modeles = importlib.import_module(f"{p}_core.models")
    session_mod = importlib.import_module(f"{p}_core.db.session")
    async with session_mod.get_async_session() as db:
        ligne = (
            await db.execute(
                select(modeles.TestExecution.id, modeles.TestExecution.status)
                .order_by(modeles.TestExecution.id.desc())
                .limit(1)
            )
        ).one()
        return int(ligne[0]), str(ligne[1])


def main() -> None:
    """Point d'entree en ligne de commande."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sortie", default="metriques_demo.json", help="Fichier JSON ecrit")
    parser.add_argument("--champs", type=int, default=40, help="Champs a verite humaine")
    args = parser.parse_args()

    base_travail = os.environ.get("POSTGRES_DB") or _lire_env("POSTGRES_DB")
    if not base_travail:
        raise SystemExit("POSTGRES_DB absent du .env et de l'environnement")
    base_demo = base_travail.removesuffix(SUFFIXE_BASE) + SUFFIXE_BASE

    if base_demo == base_travail:
        print(f" [1/6] base de demo {base_demo} (POSTGRES_DB vise deja la demo)")
    else:
        print(f" [1/6] base de demo {base_demo} (la base {base_travail} n'est pas touchee)")
    asyncio.run(_creer_base(base_demo))
    # Tout ce qui suit, sous-processus compris, vise la base de demo.
    os.environ["POSTGRES_DB"] = base_demo
    importlib.import_module(f"{_prefixe()}_core.core.config").get_core_settings.cache_clear()

    print(" [2/6] seed --reset --fake-ocr")
    _lancer("seed.py", "--reset", "--fake-ocr")

    session_mod = importlib.import_module(f"{_prefixe()}_core.db.session")
    core = importlib.import_module(f"{_prefixe()}_core.core.config").get_core_settings()
    session_mod.init_engine(core.async_database_url)

    dataset_id, document_id, file_id, detectees = asyncio.run(_poser_verite(args.champs))
    print(
        f" [3/6] verite humaine : dataset_id={dataset_id} document_id={document_id}, "
        f"{args.champs} champ(s), {len(detectees)} lu(s) par le moteur"
    )

    print(" [4/6] recette et execution")
    _lancer(
        "creer_execution_test.py", "--dataset-id", str(dataset_id), "--documents", str(document_id)
    )

    with tempfile.TemporaryDirectory(prefix="demo_metriques_") as pvc:
        print(" [5/6] worker de benchmark, un passage")
        session_mod.init_engine(core.async_database_url)
        asyncio.run(_benchmark(file_id, detectees, Path(pvc)))

    session_mod.init_engine(core.async_database_url)
    execution_id, statut = asyncio.run(_derniere_execution())
    if not statut.endswith("COMPLETED"):
        raise SystemExit(f"execution {execution_id} en {statut} : voir les logs du worker")
    session_mod.init_engine(core.async_database_url)
    resultat = asyncio.run(_metriques(execution_id))
    sortie = Path(args.sortie)
    sortie.write_text(
        json.dumps(resultat, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f" [6/6] execution_id={execution_id} : metriques ecrites dans {sortie.resolve()}")


def _lire_env(cle: str) -> str:
    """Valeur d'une cle du .env de la racine, sans dependre de pydantic."""
    fichier = ROOT / ".env"
    if not fichier.is_file():
        return ""
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        if ligne.strip().startswith(f"{cle}="):
            return ligne.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


if __name__ == "__main__":
    main()
