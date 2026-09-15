# ADAM - Annotation et Données Automatisées

uv run python -c "import sys;sys.path.insert(0,'src');import httpx;from nota_api.core.config import settings as s;r=httpx.get(s.mistral_ocr_endpoint.rstrip('/')+'/v1/models',headers={'Authorization':'Bearer '+s.mistral_api_key},verify=s.mistral_ca_bundle or True,timeout=30);print(r.status_code);print(r.text[:2000])"
