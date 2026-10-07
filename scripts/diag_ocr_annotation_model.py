"""Sonde : /v1/ocr laisse-t-il choisir le modele qui annote ?

L'annotation structuree n'est pas rendue par le modele OCR : l'endpoint la
delegue a un modele de completion, et le defaut du serveur est
mistral-small-2503. Sur un deploiement qui ne sert que du medium, la requete
tombe en 404 alors que la route existe et que /v1/ocr nu repond 200.

Reste a savoir si le client peut imposer ce modele. Le nom du parametre n'est
pas documente cote deploiement prive, donc on essaie les candidats plausibles
d'affilee plutot qu'un par un a la main. Un 200, ou seulement un message qui
cesse de nommer mistral-small-2503, designe le bon.

Quatre echecs identiques ferment la question : il faut alors annoter soi-meme,
en enchainant /v1/ocr nu puis /v1/chat/completions.

    uv run python scripts/diag_ocr_annotation_model.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx

try:
    from nota_api.core.config import settings as s
except ImportError:
    from adam_api.core.config import settings as s

B = s.mistral_ocr_endpoint.rstrip("/")
H = {"Authorization": f"Bearer {s.mistral_api_key}"}
V = s.mistral_ca_bundle or True
IMG = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
FMT = {
    "type": "json_schema",
    "json_schema": {
        "name": "sonde",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "required": ["a"],
            "additionalProperties": False,
        },
    },
}
M = "mistral-medium-latest"

CANDIDATS = [
    ("document_annotation_model", {"document_annotation_model": M}, FMT),
    ("annotation_model", {"annotation_model": M}, FMT),
    ("completion_model", {"completion_model": M}, FMT),
    ("model dans document_annotation_format", {}, dict(FMT, model=M)),
]

for nom, extra, fmt in CANDIDATS:
    payload = {
        "model": s.mistral_ocr_model,
        "document": {"type": "image_url", "image_url": IMG},
        "document_annotation_format": fmt,
        "include_image_base64": False,
    }
    payload.update(extra)
    try:
        r = httpx.post(B + "/v1/ocr", headers=H, json=payload, verify=V, timeout=60)
        corps = r.text[:220]
    except Exception as exc:  # noqa: BLE001
        r, corps = None, f"{type(exc).__name__} : {exc}"
    print(f"\n--- {nom}")
    print(f"    statut : {r.status_code if r is not None else 'ECHEC'}")
    print(f"    corps  : {corps}")
    if r is not None and r.status_code == 200:
        print("    >>> CE PARAMETRE MARCHE <<<")
    elif r is not None and "mistral-small-2503" not in r.text:
        print("    >>> le message a change, piste a creuser <<<")
