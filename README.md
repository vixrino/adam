# ADAM - Annotation et Données Automatisées

uv run python -c "import sys;sys.path.insert(0,'src');import httpx;from nota_api.core.config import settings as s;b=s.mistral_ocr_endpoint.rstrip('/');r=httpx.post(b+'/v1/ocr',headers={'Authorization':'Bearer '+s.mistral_api_key},json={'model':'mistral-ocr-latest','document':{'type':'image_url','image_url':'data:image/png;base64,iVBORw0KGgo='}},verify=s.mistral_ca_bundle or True,timeout=30);print(r.status_code);print(r.text[:800])"
