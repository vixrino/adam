# Sécuriser l'API NOTA avec exa-pie

Vérifié le 17/08/2026 contre le mock FBI 2.0.6.

## 1. Ce que fait exa-pie

Module Python interne (Pypi Sofact). Il valide la signature d'un JWT et vérifie
que l'appelant a le droit d'atteindre l'URL demandée. Il ne délivre pas de token.

`PIEFastAPIMiddleware` s'insère sur chaque requête :

1. URI publique → laisse passer
2. Sinon, extrait le token de l'en-tête `Authorization` (400 si absent)
3. `verify(token, path)` → tout statut ≠ 200 est renvoyé tel quel
4. Attache le token et le contexte à la requête, puis appelle la route

## 2. Répartition des responsabilités

| | Porte quoi |
|---|---|
| **FBI** | l'identité — un matricule, rien d'autre |
| **`pie.yaml`** | grillage grossier : ce rôle peut-il toucher cette URI |
| **la base NOTA** | organisation, `platform_role`, `ProjectRole` |

Le token ne porte ni organisation ni rôle métier, et c'est voulu : FBI connaît
les agents de la Banque, pas le découpage de NOTA. Un `ProjectRole` dépend du
projet, notion qu'un token ne peut pas exprimer.

Conséquence : un agent connu de FBI mais absent de `user` reçoit **403, pas 401**.
Son token est valide, il n'est pas habilité.

## 3. Configuration

`conf/pie.yaml` (dev, `NO-VERIFIER`) et `conf/pie.prod.yaml` (`CERT-FILE`), tous
deux versionnés — aucun ne porte de secret. `PIE_CONFIG_FILE` désigne le fichier
à charger.

| Verifier | Usage |
|---|---|
| `NO-VERIFIER` | dev — aucune vérification de signature |
| `CERT-FILE` | prod — évite un appel HTTP sortant par requête entrante |

Les patterns sont évalués dans l'ordre de déclaration, du plus spécifique au plus
général.

## 4. Montage du middleware

```python
install_jwt_middleware(app)      # AVANT add_middleware(CORSMiddleware)
app.add_middleware(CORSMiddleware, ...)
```

**L'ordre est critique.** Starlette place le dernier middleware ajouté en position
la plus externe. CORS doit rester au-dessus d'exa-pie, sinon les préflights
`OPTIONS`, dépourvus d'en-tête `Authorization`, sont rejetés en 400 et le front ne
peut plus appeler l'API. `uris-by-roles` ne discrimine pas la méthode HTTP : l'ordre
de montage est le seul levier. Un test de régression le verrouille.

L'import d'`exa_pie` est tardif, à l'intérieur de `install_jwt_middleware` : bypass
actif, l'application démarre sans accès au Pypi interne.

## 5. Lire les claims — l'anomalie du connecteur

Le middleware fait `setattr(request, 'pie_token', token)` sur **son** objet
`Request`. `call_next` ne transmet que le scope ASGI, à partir duquel FastAPI
reconstruit un nouvel objet pour la route : l'attribut ne suit pas. Seul
`request.state` traverse, ce que le connecteur n'utilise pas.

L'anomalie est **silencieuse** — `getattr` rend `None`, rien ne lève.

`claims_from_request()` essaie donc trois sources :

1. `getattr(request, "pie_context", None)`
2. `getattr(request, "pie_token", None)`
3. **l'en-tête `Authorization`** — en pratique la seule qui serve

Relire l'en-tête ne contourne rien : cette fonction n'est atteinte que si `verify()`
a rendu 200, sinon le middleware a déjà répondu.

> À remonter à l'équipe EXA PYTHON : `request.state.pie_token = token` réglerait
> le problème chez eux.

## 6. Le claim de matricule

`preferred_username` **n'existe pas** dans un token FBI. Charge utile réelle du
mock, réduite :

```json
{
  "sub": "I659418", "prn": "I659418", "user_name": "I659418",
  "uid": "i659418", "authorities": ["OPERATOR"],
  "iss": "FBI-MOCK-SERVER", "oracle.oauth.client_origin_id": "FBI-Appli-Demo"
}
```

Quatre claims portent le matricule et **ne s'accordent pas sur la casse**. L'ordre
retenu est `sub` (RFC 7519), `prn` (convention Oracle), `user_name` (Spring OAuth2).
`uid` est écarté, il porte la casse saisie par l'agent.

La comparaison en base est insensible à la casse et aux espaces.

## 7. get_caller

```
Authorization ─► exa-pie valide ─► claims_from_request
                                   └─► principal_from_claims → "I659418"
                                       └─► resolve_caller → SELECT user
                                           └─► UserCaller(matricule, org, platform_role)
```

Deux contraintes non négociables :

**Pas de `Depends(get_db)`** — dépendance circulaire, `get_db` dépend de
`get_caller` pour connaître l'organisation à poser en session. `resolve_caller`
ouvre sa propre session **non scopée** : le filtrage dérive du caller, on ne peut
pas l'appliquer pour le résoudre.

**Le bypass DEV ne lit pas le token.** Middleware non monté, aucune signature
vérifiée : lire le token laisserait n'importe qui poser `"sub": "<matricule
d'administrateur>"` et obtenir ses droits. Le bypass endosse `API_DEV_MATRICULE`
et ignore l'en-tête. Il passe malgré tout par la base, pour que le périmètre
observé en DEV soit celui d'une vraie personne.

## 8. Recette

Mock sur 9000, API sur 8000.

```powershell
curl.exe --noproxy localhost -XPOST localhost:9000/oauth/token `
  --data-urlencode "client_id=FBI-Appli-Demo" --data-urlencode "grant_type=password" `
  --data-urlencode "username=i659418" --data-urlencode "password=motdepasse"

Invoke-RestMethod "http://localhost:8000/api/v1/projects" -Headers @{Authorization="Bearer $op"}
```

| Appelant | Attendu | Statut |
|---|---|---|
| aucun token | 400 « token not found » | ✅ |
| `I659418` — `OPERATOR` | 1 projet | ✅ |
| `V654846` — `BUSINESS_ADMIN` | 2 projets | ✅ |

Le mock 2.0.6 ne démarre pas sur Java 11+ sans
`-Dcom.sun.xml.bind.v2.bytecode.ClassTailor.noOptimize=true` : JAXB y génère du
bytecode via `sun.misc.Unsafe.defineClass`, supprimée depuis.

## 9. Reste à faire

1. **Vérifier `uris-by-roles`** — `mode: KEYCLOAK` lit `realm_access.roles`, absent
   du token FBI qui porte `authorities`. Le filtrage par URI ne filtre peut-être
   rien. Test : appeler `/organisations` (réservée `ADMIN`) avec un token `OPERATOR`,
   un **403** confirme. Sinon basculer en `mode: FBI`.
2. Remonter l'anomalie `setattr` à l'équipe EXA PYTHON
3. Appliquer `require_user` / `require_roles` router par router
4. Retirer `agent_id` de `JobIn`, le déduire de l'appelant
5. `PIE_CONFIG_FILE` posé dans `conftest.py` pour les tests
6. Certificat SSO par secret, jamais versionné ; renouvellement en procédure
7. `internal_auth_enabled=true` en production
8. Supprimer `api_disable_jwt_validation` — **en dernier**, après le point 3, sinon
   plus aucun développement n'est possible sans mock FBI

## Liens

- Mock FBI OAuth2 — Confluence SOFACT
- `conf/pie.yaml`, `src/nota_api/core/security.py`, `src/nota_api/dependencies/auth.py`
