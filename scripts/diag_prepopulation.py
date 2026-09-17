"""Diagnostic de la pre-alimentation, du document en base jusqu'au merge.

PrepopulationWorker peut produire un document entierement vide sans lever la
moindre erreur : un OCR qui ne detecte rien et un schema dont aucune cle ne
correspond donnent le meme resultat silencieux. Ce script rejoue sa sequence
sur un document reel, palier par palier, et nomme le premier qui casse.

    uv run python scripts/diag_prepopulation.py <document_id>
    uv run python scripts/diag_prepopulation.py <document_id> --show-values

Aucune ecriture : ni champ cree, ni statut modifie. Les valeurs extraites sont
masquees par defaut (IBAN, NIR) ; --show-values les affiche, a reserver aux
documents fictifs.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402

from adam_api.core.config import API_PREFIX, settings  # noqa: E402
from adam_core.db.session import get_async_session  # noqa: E402
from adam_core.models import Document  # noqa: E402
from adam_worker.connectors import connector_from_settings  # noqa: E402
from adam_worker.prepopulation.api_client import ApiClient, ApiClientError  # noqa: E402
from adam_worker.prepopulation.merger import count_detected, merge, semantic_key  # noqa: E402
from adam_worker.prepopulation.poller import _api_origin, default_pages_dir  # noqa: E402

SEP = "=" * 70


def line(title: str) -> None:
    print("\n" + SEP)
    print(title)
    print(SEP)


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show_values = "--show-values" in sys.argv
    if len(args) != 1:
        raise SystemExit(__doc__)
    document_id = int(args[0])

    # -- 1. Le document -----------------------------------------------------
    line(f"1. Document {document_id}")
    async with get_async_session() as db:
        row = (
            await db.execute(
                select(Document.dataset_id, Document.file_id, Document.status).where(
                    Document.id == document_id
                )
            )
        ).one_or_none()
    if row is None:
        raise SystemExit(f"document {document_id} introuvable")
    dataset_id, file_id, status = int(row.dataset_id), int(row.file_id), row.status
    print(f"  dataset_id = {dataset_id}")
    print(f"  file_id    = {file_id}")
    print(f"  status     = {status}")

    # -- 2. Les images de page ---------------------------------------------
    line("2. Images de page lues par le worker")
    directory = Path(settings.pvc_mount_path) / default_pages_dir(file_id)
    print(f"  repertoire = {directory}")
    if not directory.is_dir():
        print("  ECHEC : repertoire absent. Le connecteur recevra une liste vide")
        print("  et tous les champs seront crees sans valeur, sans erreur.")
        return
    images = sorted(directory.glob("*.png"))
    print(f"  {len(images)} image(s) : {', '.join(p.name for p in images[:12])}")
    if not images:
        print("  ECHEC : aucune image. Meme consequence que ci-dessus.")
        return

    # -- 3. Le connecteur ---------------------------------------------------
    line("3. Connecteur OCR")
    connector = connector_from_settings(settings)
    print(f"  connecteur = {connector.name}")
    if connector.name == "mock":
        print("  ATTENTION : mock sans detected_keys, il rend un document vide.")
    else:
        print(f"  endpoint   = {settings.mistral_ocr_endpoint}")
        pages = sorted(getattr(connector, "page_fields", {}))
        print(f"  pages decrites par le schema CERFA : {pages}")
        hors = [n for n in range(1, len(images) + 1) if n not in pages]
        print(f"  pages du document non soumises     : {hors}")

    ocr = await connector.extract(images)
    if ocr is None:
        print("\n  ECHEC : extract() rend None, aucun champ detecte sur aucune page.")
        print("  Verifier que la pagination du PDF correspond aux pages ci-dessus.")
        return

    pairs = [(page, kv) for page, _, kv in ocr.iter_kv_pairs() if kv.value is not None]
    print(f"\n  {len(pairs)} champ(s) detecte(s) par l'OCR")
    for page, kv in pairs[:10]:
        shown = kv.extracted_value if show_values else "***"
        print(f"    p{page}  {kv.id:50s} = {shown}")
    if len(pairs) > 10:
        print(f"    ... et {len(pairs) - 10} autre(s)")

    # -- 4. Le schema attendu ----------------------------------------------
    line("4. Schema du dataset, via l'API")
    api = ApiClient(
        base_url=f"{_api_origin()}{API_PREFIX}",
        api_key=settings.internal_api_key,
        timeout_seconds=float(settings.ocr_timeout_seconds),
    )
    try:
        specs = await api.get_field_specs(dataset_id)
    except ApiClientError as exc:
        print(f"  ECHEC : {exc}")
        await api.aclose()
        return
    finally:
        pass
    print(f"  {len(specs)} field_spec(s)")
    schema_keys = {semantic_key(s.get("section_id"), s["field_key"]) for s in specs}
    for key in sorted(schema_keys)[:10]:
        print(f"    {key}")
    if len(schema_keys) > 10:
        print(f"    ... et {len(schema_keys) - 10} autre(s)")

    # -- 5. Le rapprochement ------------------------------------------------
    line("5. Rapprochement OCR <-> schema")
    ocr_keys = {kv.id for _, kv in pairs}
    commun = ocr_keys & schema_keys
    print(f"  cles OCR avec valeur      : {len(ocr_keys)}")
    print(f"  cles du schema            : {len(schema_keys)}")
    print(f"  cles communes             : {len(commun)}")
    if not commun:
        print("\n  CAUSE TROUVEE : aucune cle commune.")
        print("  L'OCR detecte bien, mais le dataset pointe un autre schema.")
        print("  Exemples de cles OCR orphelines :")
        for key in sorted(ocr_keys)[:5]:
            print(f"    {key}")
        print("  Exemples de cles du schema jamais vues par l'OCR :")
        for key in sorted(schema_keys - ocr_keys)[:5]:
            print(f"    {key}")

    payloads = merge(specs, ocr)
    print(f"\n  merge() : {len(payloads)} champ(s), {count_detected(payloads)} avec ocr_value")
    if payloads and count_detected(payloads) == 0:
        print("  C'est exactement ce que l'API rendra : ocr_value null partout.")

    await api.aclose()
    close = getattr(connector, "aclose", None)
    if close is not None:
        await close()


if __name__ == "__main__":
    asyncio.run(main())
