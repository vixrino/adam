# Export du connecteur Mistral pour NOTA

Fichiers a copier TELS QUELS (imports deja renommes nota_*) — ne pas retaper :

    nota_worker/connectors/mistral.py        -> src/nota_worker/connectors/mistral.py
    nota_worker/connectors/cerfa_schema.py   -> src/nota_worker/connectors/cerfa_schema.py
    nota_worker/connectors/__init__.py       -> src/nota_worker/connectors/__init__.py
    tests_unit/test_connector_mistral.py     -> tests/unit/test_connector_mistral.py
    scripts/test_mistral_connector.py        -> scripts/test_mistral_connector.py

Ces cinq copies REMPLACENT toute version precedente cote NOTA. Le point
d'entree du connecteur est `extract(images)` ; s'il reste un `ocr_document`
quelque part, c'est un vestige a supprimer.

## 4 retouches a la main

1. src/nota_worker/prepopulation/poller.py — deux lignes :

       - from nota_worker.connectors.mock import MockOcrConnector
       + from nota_worker.connectors import connector_from_settings

       - self.connector = connector or MockOcrConnector()
       + self.connector = connector or connector_from_settings(settings)

2. src/nota_api/core/config.py — apres ocr_timeout_seconds :

       mistral_api_key: str = ""
       mistral_ocr_endpoint: str = ""
       mistral_ocr_model: str = "mistral-ocr-latest"
       mistral_ca_bundle: str = ""

3. pyproject.toml — httpx passe des extras dev aux dependances :

       "httpx>=0.27.0",

   puis `uv sync`.

4. .env (et .env.template sans les valeurs) :

       OCR_MOCK_ENABLED=false
       MISTRAL_API_KEY=<cle>
       MISTRAL_OCR_ENDPOINT=https://api.mistral-outscale.pr01.ai4all.app.private
       MISTRAL_OCR_MODEL=mistral-ocr-latest
       MISTRAL_CA_BUNDLE=https.truststore.pem

## Verification

    uv run pytest tests/unit/test_connector_mistral.py -v
    uv run python scripts/test_mistral_connector.py chemin/vers/cerfa_fictif.pdf
