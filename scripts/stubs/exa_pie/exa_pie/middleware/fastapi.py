"""Sandbox stand-in for exa_pie.middleware.fastapi (the internal package is not reachable here).

What it reproduces, so adam_api.dependencies.auth runs its real path (claims -> principal ->
user lookup -> 403 for unknown matricules):
  * a missing / non-Bearer Authorization header is rejected with 400 (OPTIONS preflights included,
    which is why security.py insists on mounting CORS outside this middleware);
  * a token that is not a decodable 3-part JWT, or is expired, is rejected with 401;
  * request.pie_token is set on the middleware's own Request, like the real connector.

What it does NOT do: verify the signature, or apply the URI/role filter of conf/pie.yaml.
Assumption: requests carrying X-Internal-Token (service-to-service) and the API docs pass
through; get_caller validates the former itself.
"""

import base64
import json
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

_OPEN_PATHS = {"/docs", "/redoc", "/openapi.json"}


def _payload(token: str):
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        raw = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(raw))
    except (ValueError, UnicodeDecodeError):
        return None
    return claims if isinstance(claims, dict) else None


class PIEFastAPIMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path in _OPEN_PATHS or "X-Internal-Token" in request.headers:
            return await call_next(request)

        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return JSONResponse({"detail": "Authorization Bearer manquant"}, status_code=400)

        claims = _payload(token.strip())
        if claims is None or float(claims.get("exp", float("inf"))) < time.time():
            return JSONResponse({"detail": "Token invalide ou expire"}, status_code=401)

        request.pie_token = token.strip()
        return await call_next(request)
