"""SNIPPET : validation "PDF uniquement" a greffer dans l'ingestion de nota.

Constat : nota accepte n'importe quel type de fichier (un .md passe).
Consequence grave : le worker retente le rendu du document toutes les
5 secondes pour toujours (PdfRenderError -> reste RECEIVED -> re-candidat).

Trois greffes, dans l'ordre :

1. Dans nota_api/services/ingestion.py (si absente) : la fonction
   looks_like_pdf ci-dessous. Elle valide les OCTETS via pymupdf —
   jamais l'extension ni le content-type, qui sont falsifiables.

2. Dans le router d'ingestion de nota (POST /datasets/{id}/documents),
   au debut de la boucle sur les fichiers uploades : le bloc de rejet.

3. Dans les schemas de reponse de nota : verifier que l'item par fichier
   accepte status="rejected" et un champ reason optionnel, et que la
   reponse globale a un compteur rejected. Sinon, ajouter ces champs.
"""

# --- 1. nota_api/services/ingestion.py --------------------------------------

from typing import cast

import pymupdf


def looks_like_pdf(content: bytes) -> bool:
    """Valide que le contenu est un PDF structurellement correct (via pymupdf).

    content-type et nom de fichier sont fournis par le client et donc
    falsifiables : ils ne sont jamais utilises comme critere de validation.
    """
    try:
        doc = pymupdf.open(stream=content, filetype="pdf")  # type: ignore[no-untyped-call]
    except RuntimeError:
        return False
    try:
        return cast(int, doc.page_count) > 0
    finally:
        doc.close()  # type: ignore[no-untyped-call]


# --- 2. router d'ingestion : bloc a inserer dans la boucle `for upload in files:`
#        juste apres `content = await upload.read()` et AVANT l'appel a ingest_pdf
#        (+ import : from nota_api.services.ingestion import looks_like_pdf)

#    if not looks_like_pdf(content):
#        logger.warning(
#            "Fichier ignore (non PDF) [dataset_id=%s file_name=%s]", dataset_id, file_name
#        )
#        items.append(
#            FileIngestionItemOut(file_name=file_name, status="rejected", reason="non-PDF")
#        )
#        continue


# --- 3. test a ajouter dans le test du router d'ingestion de nota ------------
#        (adapter les fixtures client/mock_db a celles du fichier existant)

#    def test_non_pdf_content_rejected(self, client, mock_db, monkeypatch, tmp_path):
#        monkeypatch.setattr("nota_api.routers.datasets.settings.pvc_mount_path", str(tmp_path))
#        mock_db.get = AsyncMock(side_effect=_db_get_side_effect(dataset=_make_dataset()))
#
#        response = client.post(
#            "/datasets/1/documents",
#            files=[("files", ("fake.pdf", b"not a real pdf", "application/pdf"))],
#        )
#
#        assert response.status_code == 200
#        body = response.json()
#        assert body["created"] == 0
#        assert body["rejected"] == 1
#        assert body["results"][0]["status"] == "rejected"
#        assert body["results"][0]["reason"] == "non-PDF"
#        mock_db.execute.assert_not_awaited()  # rejete avant tout acces DB
