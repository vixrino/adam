# ADAM - Annotation et Données Automatisées

uv run python -c "import sys;sys.path.insert(0,'src');import httpx,json;from nota_api.core.config import settings as s;b=s.mistral_ocr_endpoint.rstrip('/');r=httpx.get(b+'/openapi.json',headers={'Authorization':'Bearer '+s.mistral_api_key},verify=s.mistral_ca_bundle or True,timeout=30);print(r.status_code);d=r.json() if r.is_success else {};print(json.dumps({k:list(v.get('properties',{}).keys()) for k,v in d.get('components',{}).get('schemas',{}).items() if 'ocr' in k.lower() or 'annotation' in k.lower()},indent=2)[:3000])"
