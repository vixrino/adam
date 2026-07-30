"""Test manuel de bout en bout du PageImageWorker.

Le script fabrique tout ce dont le worker a besoin, le fait tourner sur un seul
cycle, verifie le resultat, puis nettoie derriere lui.

Deroule
-------
1. Genere un PDF de N pages avec PyMuPDF, ou reprend celui passe en --pdf.
2. L'ecrit dans le PVC (settings.pvc_mount_path) a l'emplacement attendu.
3. Cree la chaine minimale en base : Organisation, Project, DocSchema, Dataset,
   File, puis un Document en statut RECEIVED.
4. Appelle une seule fois PageImageWorker.poll(), sans boucle infinie.
5. Verifie les trois effets attendus : un PNG par page dans file_id/pages/,
   FILE.page_count renseigne, DOCUMENT.status passe a IN_PROGRESS.
6. Supprime les lignes creees et les fichiers ecrits, sauf si --keep.

Usage
-----
    python scripts/test_page_image_worker.py                 # PDF valide, 3 pages
    python scripts/test_page_image_worker.py --pages 10
    python scripts/test_page_image_worker.py --pdf mon.pdf   # PDF existant
    python scripts/test_page_image_worker.py --corrupt       # verifie le poison pill
    python scripts/test_page_image_worker.py --keep          # ne nettoie pas

Le mode --corrupt ecrit un PDF tronque pour verifier le comportement decrit en
CA-5 : le document doit finir en ERROR et non rester en RECEIVED, sinon il
serait repolle indefiniment.

Prerequis : la base doit etre accessible et migree (les variables POSTGRES_* du
.env sont utilisees telles quelles).
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import uuid
from pathlib import Path
from typing import Tuple

# Le script est lance depuis la racine du depot : on expose src/ au PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import fitz  # PyMuPDF  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from adam_api.core.config import settings  # noqa: E402
from adam_core.core.config import get_core_settings  # noqa: E402
from adam_core.db.session import get_async_session, init_engine  # noqa: E402
from adam_core.enums.status import DocumentStatus  # noqa: E402
from adam_core.models import (  # noqa: E402
    Dataset,
    DocSchema,
    Document,
    File,
    Organisation,
    Project,
)
from adam_core.utils.hashing import sha256_file  # noqa: E402
from adam_core.utils.logging import setup_logging  # noqa: E402
from adam_core.utils.pdf_render import pages_relative_dir  # noqa: E402
from adam_worker.page_image_worker import PageImageWorker  # noqa: E402

# Suffixe unique par execution : evite toute collision avec des donnees
# existantes et permet de retrouver ce que le script a cree.
RUN_ID = uuid.uuid4().hex[:8]

#: Prefixe conserve par --corrupt. Assez court pour qu'aucun objet PDF complet
#: ne subsiste, quel que soit le nombre de pages du fichier d'origine.
_CORRUPT_PREFIX_BYTES = 256


# ---------------------------------------------------------------------------
# Affichage
# ---------------------------------------------------------------------------


def step(message: str) -> None:
    """Affiche une etape du deroule."""
    print(f"\n  {message}")


def ok(message: str) -> None:
    """Affiche une verification reussie."""
    print(f"    [OK] {message}")


def ko(message: str) -> None:
    """Affiche une verification en echec."""
    print(f"    [KO] {message}")


# ---------------------------------------------------------------------------
# Fabrication du PDF
# ---------------------------------------------------------------------------


def build_pdf(destination: Path, pages: int) -> None:
    """Ecrit un PDF valide de `pages` pages, une ligne de texte par page."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    try:
        for number in range(1, pages + 1):
            page = document.new_page()
            page.insert_text((72, 144), f"Page {number} / {pages}", fontsize=24)
        document.save(str(destination))
    finally:
        document.close()


def _is_unreadable(path: Path) -> bool:
    """Vrai si PyMuPDF echoue a ouvrir le fichier ou n'y trouve aucune page."""
    try:
        with fitz.open(str(path)) as document:
            return document.page_count == 0
    except Exception:
        return True


def build_corrupt_pdf(destination: Path, pages: int) -> None:
    """Ecrit un PDF illisible par PyMuPDF, pour tester le poison pill.

    Attention au faux negatif : PyMuPDF reconstruit la table xref d'un PDF
    tronque et rouvre sans broncher un fichier coupe a la moitie, pages
    comprises. Une troncature proportionnelle ne garantit donc rien. On coupe
    ici a un prefixe fixe et court, puis on VERIFIE que le resultat est bien
    illisible, avec un repli sur un en-tete suivi d'octets arbitraires. Sans ce
    controle, le test du poison pill passerait en ne testant rien.
    """
    build_pdf(destination, pages)
    payload = destination.read_bytes()

    destination.write_bytes(payload[:_CORRUPT_PREFIX_BYTES])
    if _is_unreadable(destination):
        return

    destination.write_bytes(b"%PDF-1.7\n" + b"\x00\xff" * 512)
    if _is_unreadable(destination):
        return

    raise RuntimeError(
        "impossible de fabriquer un PDF illisible : PyMuPDF lit encore le "
        "fichier corrompu, le test du poison pill serait vide"
    )


# ---------------------------------------------------------------------------
# Preparation de la base
# ---------------------------------------------------------------------------


async def create_fixtures(pdf_relative_path: str, pdf_absolute_path: Path) -> Tuple[int, int]:
    """Cree la chaine Organisation -> Document et retourne (document_id, file_id)."""
    async with get_async_session() as db:
        organisation = Organisation(
            name=f"Org Test Worker {RUN_ID}",
            slug=f"test-worker-{RUN_ID}",
        )
        db.add(organisation)
        await db.flush()

        project = Project(
            organisation_id=organisation.id,
            name=f"Projet Test Worker {RUN_ID}",
            description="Cree par scripts/test_page_image_worker.py",
        )
        db.add(project)
        await db.flush()

        doc_schema = DocSchema(
            project_id=project.id,
            version=1,
            name=f"Schema Test Worker {RUN_ID}",
            document_type="TEST_WORKER",
        )
        db.add(doc_schema)
        await db.flush()

        dataset = Dataset(
            project_id=project.id,
            schema_id=doc_schema.id,
            name=f"Dataset Test Worker {RUN_ID}",
        )
        db.add(dataset)
        await db.flush()

        file_row = File(
            file_path=pdf_relative_path,
            file_size_bytes=pdf_absolute_path.stat().st_size,
            sha256_checksum=sha256_file(pdf_absolute_path),
            # Volontairement laisse a sa valeur par defaut : c'est le worker qui
            # doit le renseigner, et le verifier prouve qu'il a bien travaille.
        )
        db.add(file_row)
        await db.flush()

        document = Document(
            dataset_id=dataset.id,
            file_id=file_row.id,
            file_name=pdf_absolute_path.name,
            status=DocumentStatus.RECEIVED.value,
        )
        db.add(document)
        await db.flush()

        return document.id, file_row.id


# ---------------------------------------------------------------------------
# Verifications
# ---------------------------------------------------------------------------


async def check_success(
    document_id: int, file_id: int, expected_pages: int, pvc_root: Path
) -> bool:
    """Verifie les trois effets attendus d'un rendu reussi."""
    all_good = True
    async with get_async_session() as db:
        document = await db.get(Document, document_id)
        file_row = await db.get(File, file_id)
        assert document is not None and file_row is not None

        expected_status = DocumentStatus.IN_PROGRESS.value
        if document.status == expected_status:
            ok(f"DOCUMENT.status = {document.status}")
        else:
            ko(f"DOCUMENT.status = {document.status}, attendu {expected_status}")
            all_good = False

        if file_row.page_count == expected_pages:
            ok(f"FILE.page_count = {file_row.page_count}")
        else:
            ko(f"FILE.page_count = {file_row.page_count}, attendu {expected_pages}")
            all_good = False

    images_dir = pvc_root / pages_relative_dir(file_id)
    images = sorted(images_dir.glob("*.png"))
    if len(images) == expected_pages:
        ok(f"{len(images)} PNG dans {images_dir}")
    else:
        ko(f"{len(images)} PNG dans {images_dir}, attendu {expected_pages}")
        all_good = False

    # Les noms sont zero-paddes pour que le tri lexicographique suive l'ordre
    # des pages : le verifier evite une regression silencieuse cote front.
    expected_names = [f"{number:04d}.png" for number in range(1, expected_pages + 1)]
    actual_names = [image.name for image in images]
    if actual_names == expected_names:
        ok("noms zero-paddes et ordonnes")
    else:
        ko(f"noms inattendus : {actual_names[:5]}")
        all_good = False

    empty = [image.name for image in images if image.stat().st_size == 0]
    if empty:
        ko(f"images vides : {empty}")
        all_good = False
    elif images:
        ok("aucune image vide")

    return all_good


async def check_poison_pill(document_id: int, file_id: int, pvc_root: Path) -> bool:
    """Verifie qu'un PDF illisible sort de la file au lieu d'y rester (CA-5)."""
    all_good = True
    async with get_async_session() as db:
        document = await db.get(Document, document_id)
        assert document is not None

        if document.status == DocumentStatus.ERROR.value:
            ok(f"DOCUMENT.status = {document.status}")
        elif document.status == DocumentStatus.RECEIVED.value:
            ko("DOCUMENT reste en RECEIVED : il sera repolle indefiniment")
            all_good = False
        else:
            ko(f"DOCUMENT.status = {document.status}, attendu ERROR")
            all_good = False

    images_dir = pvc_root / pages_relative_dir(file_id)
    leftovers = sorted(images_dir.glob("*.png")) if images_dir.exists() else []
    if leftovers:
        ko(f"images partielles laissees derriere : {[i.name for i in leftovers]}")
        all_good = False
    else:
        ok("aucune image partielle laissee derriere")

    return all_good


# ---------------------------------------------------------------------------
# Nettoyage
# ---------------------------------------------------------------------------


async def cleanup(document_id: int, file_id: int, pvc_root: Path, pdf_path: Path) -> None:
    """Supprime les lignes creees et les fichiers ecrits, du bas vers le haut."""
    async with get_async_session() as db:
        document = await db.get(Document, document_id)
        dataset_id = document.dataset_id if document else None
        if document:
            await db.delete(document)
            await db.flush()

        file_row = await db.get(File, file_id)
        if file_row:
            await db.delete(file_row)
            await db.flush()

        if dataset_id is not None:
            dataset = await db.get(Dataset, dataset_id)
            project_id = dataset.project_id if dataset else None
            if dataset:
                await db.delete(dataset)
                await db.flush()
            if project_id is not None:
                await db.execute(delete(DocSchema).where(DocSchema.project_id == project_id))
                project = await db.get(Project, project_id)
                organisation_id = project.organisation_id if project else None
                if project:
                    await db.delete(project)
                    await db.flush()
                if organisation_id is not None:
                    organisation = await db.get(Organisation, organisation_id)
                    if organisation:
                        await db.delete(organisation)

    shutil.rmtree(pvc_root / pages_relative_dir(file_id), ignore_errors=True)
    pdf_path.unlink(missing_ok=True)


async def orphan_count() -> int:
    """Nombre de lignes laissees par d'anciennes executions du script."""
    async with get_async_session() as db:
        rows = (
            (
                await db.execute(
                    select(Organisation.slug).where(Organisation.slug.like("test-worker-%"))
                )
            )
            .scalars()
            .all()
        )
        return len(rows)


# ---------------------------------------------------------------------------
# Enchainement
# ---------------------------------------------------------------------------


async def main(args: argparse.Namespace) -> int:
    core = get_core_settings()
    setup_logging(core)
    init_engine(core.async_database_url, echo=False)

    pvc_root = Path(settings.pvc_mount_path)
    pdf_relative_path = f"test-worker-{RUN_ID}/source.pdf"
    pdf_absolute_path = pvc_root / pdf_relative_path

    print(f"\n=== Test PageImageWorker (run {RUN_ID}) ===")
    print(f"  PVC   : {pvc_root.resolve()}")
    print(f"  Base  : {core.async_database_url.split('@')[-1]}")

    step("1. Preparation du PDF")
    if args.pdf:
        source = Path(args.pdf)
        if not source.is_file():
            print(f"    [KO] fichier introuvable : {source}")
            return 1
        pdf_absolute_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, pdf_absolute_path)
        expected_pages = fitz.open(str(pdf_absolute_path)).page_count
        ok(f"copie de {source} ({expected_pages} page(s))")
    elif args.corrupt:
        build_corrupt_pdf(pdf_absolute_path, args.pages)
        expected_pages = args.pages
        ok(f"PDF tronque de {pdf_absolute_path.stat().st_size} octets")
    else:
        build_pdf(pdf_absolute_path, args.pages)
        expected_pages = args.pages
        ok(f"PDF valide de {expected_pages} page(s)")

    step("2. Creation des donnees en base")
    document_id, file_id = await create_fixtures(pdf_relative_path, pdf_absolute_path)
    ok(f"document_id={document_id} file_id={file_id} status=RECEIVED")

    step("3. Execution d'un cycle du worker")
    worker = PageImageWorker(pvc_root=pvc_root)
    await worker.poll()

    step("4. Verifications")
    if args.corrupt:
        success = await check_poison_pill(document_id, file_id, pvc_root)
    else:
        success = await check_success(document_id, file_id, expected_pages, pvc_root)

    if args.keep:
        step("5. Nettoyage ignore (--keep)")
        print(f"    document_id={document_id} file_id={file_id}")
        print(f"    images : {(pvc_root / pages_relative_dir(file_id)).resolve()}")
    else:
        step("5. Nettoyage")
        await cleanup(document_id, file_id, pvc_root, pdf_absolute_path)
        ok("lignes et fichiers supprimes")
        orphans = await orphan_count()
        if orphans:
            print(f"    [i] {orphans} organisation(s) test-worker-* d'anciennes executions")

    print(f"\n=== {'SUCCES' if success else 'ECHEC'} ===\n")
    return 0 if success else 1


def parse_args() -> argparse.Namespace:
    """Analyse les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(description="Test de bout en bout du PageImageWorker.")
    parser.add_argument("--pages", type=int, default=3, help="nombre de pages du PDF genere")
    parser.add_argument("--pdf", type=str, default=None, help="chemin d'un PDF existant a utiliser")
    parser.add_argument(
        "--corrupt",
        action="store_true",
        help="ecrit un PDF tronque et verifie le passage en ERROR (poison pill)",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="conserve les donnees et les images pour inspection",
    )
    return parser.parse_args()


if __name__ == "__main__":
    parsed = parse_args()
    if parsed.pdf and parsed.corrupt:
        print("--pdf et --corrupt sont exclusifs.")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(parsed)))
