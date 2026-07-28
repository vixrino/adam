# Sécuriser l'API NOTA avec exa-pie

## Table des matières

1. [Ce qu'est exa-pie](#1-ce-quest-exa-pie)
2. [Pourquoi NOTA en a besoin](#2-pourquoi-nota-en-a-besoin)
3. [Décisions prises](#3-décisions-prises)
4. [Installation](#4-installation)
5. [Configuration : `conf/pie.yaml`](#5-configuration--confpieyaml)
6. [Branchement du middleware](#6-branchement-du-middleware)
7. [Récupération du contexte utilisateur](#7-récupération-du-contexte-utilisateur)
8. [Réécriture de `get_caller()`](#8-réécriture-de-get_caller)
9. [Contrôle fin des droits](#9-contrôle-fin-des-droits)
10. [Appels machine](#10-appels-machine)
11. [Limites à connaître](#11-limites-à-connaître)
12. [Tests](#12-tests)
13. [Hypothèses à confirmer](#13-hypothèses-à-confirmer)
14. [Checklist de mise en place](#14-checklist-de-mise-en-place)

---

## 1. Ce qu'est exa-pie

`exa-pie` est un module Python interne (Pypi Sofact) qui fait **une seule chose** :
valider le JWT d'un utilisateur et vérifier qu'il a le droit d'appeler l'URL qu'il
demande. Ce n'est pas un serveur d'authentification — c'est le côté *consommateur*.

Deux modes, selon l'IdP en face :

| Mode | Fournisseur d'identité |
|------|------------------------|
| `KEYCLOAK` | Keycloak |
| `FBI` | FBI (SSO interne) |

Le mode ne change que la façon de lire les rôles dans le token ; le reste est identique.

### Les verifiers

Pour valider la signature d'un JWT il faut la clé publique de l'IdP. Le `verifier` dit
**où** exa-pie va la chercher :

| Verifier | `value` attendue |
|----------|------------------|
| `NO-VERIFIER` | — (signature non vérifiée, **dev uniquement**) |
| `KEY-VALUE` | la clé publique en clair dans le YAML |
| `KEY-FILE` | chemin vers un fichier contenant la clé publique |
| `CERT-VALUE` | le certificat X509 en clair dans le YAML |
| `CERT-FILE` | chemin vers un `.pem` |
| `CERT-URI` | URL exposant le certificat (nécessite `ssl-verify`) |

### Ce qu'exa-pie expose

```python
from exa_pie.client import PIEClient

pie_client = PIEClient()                                   # lit conf/pie.yaml

pie_client.is_public_uri('/health')                         # -> bool
message, status = pie_client.verify(token, '/documents')    # -> (str, int)
context = pie_client.get_context(token)                     # -> claims du token
pie_client.get_user_roles(pie_context=context)              # -> liste de rôles
```

Et un middleware par framework :

| Classe | Framework |
|--------|-----------|
| `PIEDjangoMiddleware` | Django |
| `PIEFalconMiddleware` | Falcon |
| `PIEFastAPIMiddleware` | FastAPI ← celui qui nous intéresse |

Le middleware FastAPI (`exa_pie/middleware/fastapi.py`) est un `BaseHTTPMiddleware` qui,
sur chaque requête :

1. si l'URI est publique → laisse passer sans rien faire ;
2. sinon extrait le token des headers (`get_token`) → `400` si absent/malformé ;
3. appelle `verify(token, path)` → renvoie le status tel quel s'il n'est pas `200` ;
4. attache le token et le contexte à la requête, puis appelle la route.

---

## 2. Pourquoi NOTA en a besoin

Aujourd'hui dans `src/nota_api/dependencies/auth.py` :

```python
if jwt is not None:
    if settings.api_disable_jwt_validation:
        logger.critical("JWT BYPASS actif ne jamais utiliser en production")
        return UserCaller(matricule="MAT00003", organisation_id=1)
    raise HTTPException(status_code=501, detail="Auth JWT non implementee")
```

Exactement deux comportements possibles : un bypass qui renvoie un utilisateur en dur, ou
un `501`. **exa-pie remplit ce trou.**

À noter aussi : `require_user()` et `require_service()` sont définis mais **utilisés par
aucun router**. Toutes les routes de NOTA sont donc ouvertes aujourd'hui. exa-pie règle ça
globalement via `pie.yaml`, sans ajouter un `Depends` partout.

---

## 3. Décisions prises

Résumé des choix, avec leur justification. Le détail est dans les sections qui suivent.

| Sujet | Décision | Pourquoi |
|-------|----------|----------|
| Ordre des middlewares | exa-pie ajouté **avant** `CORSMiddleware` | Starlette met le dernier ajouté en position la plus externe ; CORS doit rester externe sinon exa-pie rejette les préflights `OPTIONS` en `400` |
| Verifier en prod | `CERT-FILE`, certificat fourni par un secret | Pas d'appel HTTP sortant par requête entrante, pas de dépendance runtime à la dispo du SSO |
| Verifier en dev | `NO-VERIFIER` | Permet de forger un token pour tester les rôles sans monter un Keycloak |
| Un `pie.yaml` par env ou un seul ? | Un fichier par env + `PIE_CONFIG_FILE` pour choisir | Les deux YAML ne contiennent aucun secret (juste un chemin de certificat), donc versionnables |
| Flag `PIE_ENABLED` | **Non** | Un troisième interrupteur d'auth désactivable est un risque prod. Les tests pointent `PIE_CONFIG_FILE` vers un YAML `NO-VERIFIER`, ça suffit |
| `api_disable_jwt_validation` | **À supprimer** | Devient redondant : `NO-VERIFIER` + token forgé couvre le besoin dev, sans utilisateur en dur dans le code |
| `organisation_id` | Résolu **en base** depuis le matricule | Le token ne doit pas décider du cloisonnement des données ; `User.organisation_id` est la source de vérité |
| Granularité des droits | exa-pie = zones, dépendances FastAPI = actions | `uris-by-roles` ne matche pas la méthode HTTP, il ne peut pas exprimer « GET pour tous, DELETE pour ADMIN » |
| Dépendance d'auth | Router par router, pas globale | Une dépendance globale renverrait `401` sur `/health`, que les health-checks appellent sans credentials |
| Instanciation du `PIEClient` | Paresseuse, via `@lru_cache` | Un `PIEClient()` au niveau module exigerait `pie.yaml` à l'import, ce qui casse la configuration des tests (section 8) |
| `/db-check` | Protégée `ADMIN`, pas publique | Son message d'erreur expose des détails de connexion Postgres |
| Appels machine | Rien à faire | Le worker attaque Postgres directement, il ne traverse jamais le middleware (section 10) |
| Contexte dans les routes | `request.state` + fallback `getattr` | Contourne un bug du middleware exa-pie (section 7) |

---

## 4. Installation

```bash
source .venv/bin/activate
python -m pip install exa-pie
```

Puis dans `pyproject.toml` :

```toml
dependencies = [
    # ...
    "exa-pie",
]
```

> Le module est sur le Pypi interne Sofact, pas sur le Pypi public — l'index configuré
> (`pip.conf` / `PIP_INDEX_URL`) doit pointer dessus, sinon `No matching distribution
> found`.

---

## 5. Configuration : `conf/pie.yaml`

exa-pie cherche `conf/pie.yaml` à la racine du projet, ou le chemin absolu donné par
`PIE_CONFIG_FILE`.

### Les options

| Option | Obligatoire | Défaut | Description |
|--------|-------------|--------|-------------|
| `pie.security.mode` | ⭐ | — | `FBI` ou `KEYCLOAK` |
| `pie.security.verifier` | ⭐ | — | voir le tableau des verifiers |
| `pie.security.value` | ⭐ | — | dépend du verifier |
| `pie.security.algorithms` | ⭐ | — | ex. `RS256`, `RS512` |
| `pie.security.log-level` | | `INFO` | logs du connecteur (détaillés en `DEBUG`) |
| `pie.security.ssl-verify` | | `False` | bundle CA pour le verifier `CERT-URI` |
| `pie.security.public-uris` | | — | patterns REGEX accessibles sans auth |
| `pie.security.uris-by-roles` | | — | mapping REGEX → rôles autorisés |

Trois règles sur le matching :

- les patterns sont testés **dans l'ordre de déclaration**, le premier qui matche gagne ;
- une route qui ne matche **ni** `public-uris` **ni** `uris-by-roles` reste accessible,
  mais seulement avec un token valide (aucun contrôle de rôle) ;
- sans token du tout, la requête est rejetée.

L'ordre n'est donc pas cosmétique : `^\/?documents(.*)?$` placé avant
`^\/?documents\/admin(.*)?$` rend le second inatteignable.

### `conf/pie.yaml` — dev

Les rôles reprennent l'enum `UserRole` de `nota_core/enums/roles.py` (`OPERATOR`,
`SUPERVISOR`, `ADMIN`).

```yaml
---
pie:
  security:
    mode: KEYCLOAK
    verifier: NO-VERIFIER
    algorithms:
      - RS256
    log-level: DEBUG

    # Routes techniques : ni token ni role.
    public-uris:
      - ^\/?health$
      - ^\/?docs(.*)?$
      - ^\/?redoc(.*)?$
      - ^\/?openapi\.json$
      - ^\/?static(.*)?$

    # Du plus specifique au plus general.
    uris-by-roles:
      ^\/?db-check$: ADMIN
      ^\/?organisations(.*)?$: ADMIN
      ^\/?users(.*)?$: ADMIN
      ^\/?schemas(.*)?$: ADMIN|SUPERVISOR
      ^\/?datasets(.*)?$: ADMIN|SUPERVISOR
      ^\/?projects(.*)?$: ADMIN|SUPERVISOR|OPERATOR
      ^\/?documents(.*)?$: ADMIN|SUPERVISOR|OPERATOR
      ^\/?ocr-results(.*)?$: ADMIN|SUPERVISOR|OPERATOR
      ^\/?jobs(.*)?$: ADMIN|SUPERVISOR|OPERATOR
      ^\/?files(.*)?$: ADMIN|SUPERVISOR|OPERATOR
```

`/docs` et `/openapi.json` **doivent** être publics : le navigateur charge `/openapi.json`
depuis la page Swagger sans header `Authorization`. Sans ça, la doc s'affiche vide.

`/static` est listé par anticipation. En l'état, `nota_api/static/` contient
`swagger-ui-bundle.js` et `swagger-ui.css` mais **aucun code ne les branche** : `main.py`
monte bien `/static`, sans configurer `docs_url` / `swagger_ui_parameters`, donc `/docs`
sert le HTML FastAPI par défaut qui tire ses assets d'un CDN. Le jour où le Swagger
offline sera câblé (c'est visiblement l'intention derrière ces fichiers), `/static` devra
être public — autant que ce soit déjà le cas.

`/db-check` est en `ADMIN` et non en public, même en dev : autant que le comportement dev
et prod soient identiques sur ce point, ça évite une surprise au déploiement.

### `conf/pie.prod.yaml`

```yaml
---
pie:
  security:
    mode: KEYCLOAK
    verifier: CERT-FILE
    value: /etc/nota/pie/sso.pem
    algorithms:
      - RS256
    log-level: INFO
    public-uris:
      - ^\/?health$
      - ^\/?docs(.*)?$
      - ^\/?redoc(.*)?$
      - ^\/?openapi\.json$
      - ^\/?static(.*)?$
    uris-by-roles:
      # identique au dev
```

`CERT-FILE` plutôt que `CERT-URI` pour deux raisons : pas d'appel HTTP sortant sur le
chemin critique de chaque requête, et l'API ne tombe pas si le endpoint de certificat du
SSO est indisponible. La contrepartie est qu'il faut penser à faire tourner le fichier à
l'expiration du certificat — à inscrire dans les procédures d'exploitation.

Le chemin `/etc/nota/pie/sso.pem` est une proposition : le dépôt ne contient aujourd'hui
ni `Dockerfile`, ni `docker-compose`, ni manifeste k8s, donc le mode de déploiement n'est
pas encore fixé. Ce qui compte quel que soit le support : le certificat doit être fourni
au conteneur par un secret et non versionné, et le `pie.yaml` doit pointer sur son chemin
de montage.

Sélection du fichier par environnement, dans le déploiement :

```ini
PIE_CONFIG_FILE=/app/conf/pie.prod.yaml
```

À ajouter au `.env.template` :

```ini
# Chemin absolu du fichier de conf exa-pie (defaut : conf/pie.yaml)
PIE_CONFIG_FILE=
```

---

## 6. Branchement du middleware

Dans `src/nota_api/main.py` :

```python
from exa_pie.middleware.fastapi import PIEFastAPIMiddleware

app = FastAPI(title=settings.api_title, version=settings.app_version, lifespan=lifespan)
app.add_exception_handler(Exception, http_exception_handler)

# ORDRE CRITIQUE : Starlette place le dernier middleware ajoute en position la plus
# externe. CORS doit rester externe, sinon exa-pie rejette les preflights OPTIONS
# (sans header Authorization) en 400 et le front ne peut plus appeler l'API.
# Ne pas inverser ces deux blocs.
app.add_middleware(PIEFastAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### ⚠️ Pourquoi cet ordre

Starlette **insère** chaque middleware en tête de pile : le **dernier** `add_middleware`
appelé est le plus **externe**, donc celui qui voit la requête en premier.

Si exa-pie est ajouté après CORS, il devient externe et traite les requêtes `OPTIONS` de
préflight — qui ne portent jamais de header `Authorization`. Il les rejette en `400` avant
que CORS ne puisse y répondre. Résultat : le front n'arrive plus à appeler l'API, avec une
erreur CORS opaque dans la console qui ne dit rien sur la vraie cause.

`uris-by-roles` ne permet pas de filtrer par méthode HTTP, donc on ne peut pas
« excepter les OPTIONS » dans le YAML. **Le seul levier est l'ordre des middlewares.**
D'où le commentaire dans le code : c'est le genre de ligne qu'un refactoring déplace sans
réfléchir. Le test de préflight en section 12 verrouille ce comportement.

### Le client est instancié au démarrage

`PIEFastAPIMiddleware.__init__` fait `self.pie_client = PIEClient()` : la config est lue
au montage de l'app, pas à la première requête. Si le `pie.yaml` est absent ou invalide,
**l'app ne démarre pas**. C'est le bon comportement (fail fast), mais le fichier doit être
livré avec l'application **et** disponible dans l'environnement de test — c'est ce qui
dicte la fixture de la section 12.

---

## 7. Récupération du contexte utilisateur

Le middleware pose deux informations sur la requête :

- `pie_token` — le JWT brut ;
- `pie_context` — les claims décodés.

Dans un router :

```python
from fastapi import APIRouter, Request

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("")
async def list_documents(request: Request):
    context = request.state.pie_context
    token = request.state.pie_token
    ...
```

En pratique tu passeras plutôt par la dépendance `require_user` (section 8), qui renvoie un
`UserCaller` typé — lire `request.state` directement ne sert que pour les claims bruts.

### ⚠️ `request.state`, pas `request` directement

Contrairement à Django (`request.pie_context`) et Falcon (`req.pie_context`), en FastAPI
il faut passer par `request.state`. Raison technique : avec `BaseHTTPMiddleware`, l'objet
`Request` du middleware et celui injecté dans la route sont **deux instances
différentes**, reconstruites depuis le même `scope` ASGI. Seul `request.state` (stocké
dans `scope['state']`) est partagé.

Or le code actuel du middleware exa-pie fait :

```python
setattr(request, 'pie_token', token)
setattr(request, 'pie_context', self.pie_client.get_context(token))
```

Ça pose les attributs sur l'instance du middleware, jetée juste après → la route récupère
un `AttributeError`. **Correctif à remonter à l'équipe EXA PYTHON** :

```python
request.state.pie_token = token
request.state.pie_context = self.pie_client.get_context(token)
```

En attendant, NOTA ne dépend pas du middleware pour le contexte : la dépendance
`get_caller()` le recalcule en fallback (section suivante). Ce code fonctionne avec ou
sans le correctif upstream, donc rien à changer le jour où il arrive.

### Routes publiques

Sur une route listée dans `public-uris`, le middleware ne pose rien.
`request.state.pie_context` lève un `AttributeError`. Si une route peut être appelée avec
ou sans auth :

```python
context = getattr(request.state, "pie_context", None)
```

---

## 8. Réécriture de `get_caller()`

Objectif : garder l'interface `Caller` / `UserCaller` / `ServiceCaller` — les routers n'ont
rien à changer — mais remplacer le `501` par une vraie lecture du token.

```python
"""
Auth - Detection de l'origine de la requete.
"""

import secrets
from functools import lru_cache
from typing import Optional, Union

from exa_pie.client import PIEClient
from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nota_api.core.config import settings
from nota_api.dependencies.db import get_db
from nota_core.models import User
from nota_core.utils.logging import get_logger

logger = get_logger(__name__)
_bearer = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-Internal-Token", auto_error=False)


@lru_cache
def _get_pie_client() -> PIEClient:
    """Instanciation paresseuse : importer ce module ne doit pas exiger pie.yaml."""
    return PIEClient()


class UserCaller(BaseModel):
    matricule: str
    organisation_id: int
    roles: list[str] = []


class ServiceCaller(BaseModel):
    service_name: str


Caller = Union[UserCaller, ServiceCaller]


async def get_caller(
    request: Request,
    jwt: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    api_key: Optional[str] = Depends(_api_key_header),
    db: AsyncSession = Depends(get_db),
) -> Caller:
    """Detecte l'origine - IHM ou service machine."""
    if api_key is not None:
        if not settings.internal_auth_enabled:
            logger.critical("AUTH SERVICE BYPASS actif ne jamais utiliser en production")
            return ServiceCaller(service_name="bypass-dev")
        if not secrets.compare_digest(api_key, settings.internal_api_key):
            raise HTTPException(status_code=403, detail="Token service invalide")
        return ServiceCaller(service_name="internal-service")

    if jwt is not None:
        pie = _get_pie_client()

        # Le middleware exa-pie a deja valide signature et roles : on ne fait que lire.
        # Le fallback couvre le bug setattr du middleware (cf. docs/securite-exa-pie.md).
        context = getattr(request.state, "pie_context", None)
        if context is None:
            context = pie.get_context(token=jwt.credentials)

        matricule = _extract_matricule(context)
        user = (
            await db.execute(select(User).where(User.matricule == matricule))
        ).scalar_one_or_none()
        if user is None:
            logger.warning("Token valide mais matricule %s inconnu en base", matricule)
            raise HTTPException(status_code=403, detail="Utilisateur inconnu")

        return UserCaller(
            matricule=user.matricule,
            organisation_id=user.organisation_id,
            roles=pie.get_user_roles(pie_context=context),
        )

    raise HTTPException(status_code=401, detail="Authentification requise")


def _extract_matricule(context: dict) -> str:
    matricule = context.get("preferred_username") or context.get("sub")
    if not matricule:
        raise HTTPException(status_code=401, detail="Matricule absent du token")
    return matricule
```

### Pourquoi `_get_pie_client()` et pas un `PIEClient()` au niveau module

Un `_pie_client = PIEClient()` posé directement à la racine du module lit `pie.yaml` **à
l'import**. En test, `monkeypatch.setenv("PIE_CONFIG_FILE", ...)` s'exécute au moment de la
fixture, donc *après* la collecte pytest qui a déjà importé le module : le client serait
construit avec la mauvaise configuration, ou l'import échouerait faute de fichier. Le
`@lru_cache` repousse la construction au premier appel, tout en gardant un seul client pour
le process — même idiome que `get_settings()` / `get_core_settings()` ailleurs dans NOTA.

### `organisation_id` vient de la base, pas du token

C'est le point le plus important de cette dépendance. `organisation_id` détermine quelles
données l'utilisateur voit ; le laisser venir du token signifierait que quiconque peut
influencer le contenu du token peut changer de périmètre. `User.organisation_id` en base
est la source de vérité, et le token ne sert qu'à établir *qui* appelle.

Effet de bord assumé : un utilisateur authentifié chez l'IdP mais absent de la table
`User` reçoit un `403`. C'est volontaire — il faut un provisionnement explicite dans NOTA.

### Suppression de `api_disable_jwt_validation`

Le bypass devient inutile : en dev, `NO-VERIFIER` accepte n'importe quel token forgé
(section 12), ce qui donne le même confort sans utilisateur en dur dans le code de prod.
Concrètement :

- retirer `api_disable_jwt_validation` de `Settings` dans `nota_api/core/config.py` ;
- retirer la ligne du `.env` et du `.env.template` ;
- supprimer la branche correspondante de `get_caller()` (déjà fait ci-dessus).

Reste `internal_auth_enabled`, qui garde sa raison d'être pour le chemin service.

---

## 9. Contrôle fin des droits

exa-pie donne le filtre grossier (qui peut toucher à quelle zone). Le filtre fin (qui peut
faire quoi dessus) reste en dépendances FastAPI, parce que `uris-by-roles` ne matche pas la
méthode HTTP.

Dans `nota_api/dependencies/auth.py` :

```python
from nota_core.enums.roles import UserRole


def require_roles(*roles: UserRole):
    """Fabrique une dependance exigeant au moins un des roles donnes."""
    allowed = {r.value for r in roles}

    async def _check(caller: UserCaller = Depends(require_user)) -> UserCaller:
        if not allowed & set(caller.roles):
            raise HTTPException(
                status_code=403,
                detail=f"Role requis : {' ou '.join(sorted(allowed))}",
            )
        return caller

    return _check
```

Usage :

```python
# Lecture : tous les roles autorises par pie.yaml sur /projects
@router.get("")
async def list_projects(caller: UserCaller = Depends(require_user)):
    ...

# Suppression : ADMIN uniquement
@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    caller: UserCaller = Depends(require_roles(UserRole.ADMIN)),
):
    ...
```

### Appliquer effectivement les dépendances

`require_user` n'est référencé par aucun router aujourd'hui. À déclarer **router par
router**, pas globalement :

```python
router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
    dependencies=[Depends(require_user)],
)
```

La tentation est d'écrire `FastAPI(..., dependencies=[Depends(get_caller)])` pour couvrir
tout d'un coup, mais ça s'appliquerait aussi aux routes techniques (`/health`, `/docs`),
qui n'ont pas de token → `401`. Or `/health` est exactement l'endpoint qu'un
orchestrateur ou un load balancer interroge sans credentials : le passer en `401` fait
déclarer l'application morte alors qu'elle fonctionne. La déclaration par router est plus
verbeuse mais explicite, et laisse `/health` et `/db-check` en dehors.

---

## 10. Appels machine

**Aucune action nécessaire aujourd'hui.**

Le worker (`nota_worker/`) ne passe pas par l'API : il ouvre directement une session
Postgres (`nota_core.db.session.get_async_session`) et manipule les modèles SQLAlchemy.
Vérifié — aucun `httpx` / `requests` / `aiohttp` dans `src/` ni `scripts/` ; `httpx` n'est
présent que comme dépendance de dev pour le `TestClient`. Le worker ne traverse donc jamais
le middleware exa-pie et n'est pas affecté par sa mise en place.

Le chemin `X-Internal-Token` / `require_service` existe dans `auth.py` mais n'a pas
d'appelant. Le garder ne coûte rien ; il faut juste savoir qu'il n'est pas exercé, donc pas
testé en conditions réelles.

### Le jour où un appelant machine apparaît

Un service qui appellerait l'API avec `X-Internal-Token` se ferait rejeter en `400` par
exa-pie *avant* d'atteindre `get_caller()` : le middleware ne lit que le header
`Authorization`. Plan retenu ce jour-là : préfixer les routes machine en `/internal/` et
les déclarer publiques côté exa-pie, l'authentification y restant assurée par
`require_service`.

```yaml
public-uris:
  - ^\/?internal(.*)?$
```

À plus long terme, la solution propre est un compte de service Keycloak en
`client_credentials` avec un rôle `SERVICE` dans `uris-by-roles`, ce qui fait disparaître
`X-Internal-Token` et unifie l'authentification sur un seul mécanisme.

---

## 11. Limites à connaître

**Pas de filtrage par méthode HTTP.** Traité en section 9.

**Pas de contrôle sur les ressources.** exa-pie ne sait rien de `User.organisation_id` :
un `ADMIN` de l'organisation 1 passe le middleware pour `/documents/42` même si ce document
appartient à l'organisation 2. Le cloisonnement par organisation reste **entièrement** à la
charge de NOTA, dans les requêtes des routers. C'est la faille la plus probable à
l'usage — exa-pie donne un faux sentiment de complétude sur ce point.

**Code synchrone dans un middleware async.** `verify()` et `get_context()` sont des appels
bloquants dans un `async def dispatch`, exécutés à chaque requête. Le choix de `CERT-FILE`
évite le pire cas (un appel HTTP sortant par requête), mais la vérification de signature
RSA reste dans la boucle d'événements. À mesurer avant la prod ; si ça pèse, l'option est
d'envelopper l'appel dans `run_in_threadpool`.

**`BaseHTTPMiddleware` et le streaming.** `BaseHTTPMiddleware` a des limitations connues
avec les réponses en streaming. NOTA sert des fichiers via `/files` — à vérifier si des
routes utilisent `StreamingResponse` ou `FileResponse`.

---

## 12. Tests

### Forger un token en dev

Avec `NO-VERIFIER`, la signature n'est pas vérifiée : n'importe quel JWT bien formé passe.

```python
import base64
import json


def fake_token(roles: list[str], matricule: str = "MAT00003") -> str:
    def seg(d: dict) -> str:
        raw = json.dumps(d).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = seg({"alg": "RS256", "typ": "JWT"})
    payload = seg({
        "preferred_username": matricule,
        "realm_access": {"roles": roles},
    })
    return f"{header}.{payload}.signature-bidon"
```

### Fixture de configuration

Le `PIEClient` du middleware est construit au montage de l'app : les tests ont besoin d'un
`pie.yaml` lisible **avant** que `nota_api.main` ne soit importé. Une fixture classique
arrive trop tard — l'import a lieu à la collecte. Il faut donc poser la variable au niveau
module de `conftest.py` :

```python
# tests/conftest.py — AVANT tout import de nota_api.
import os
from pathlib import Path

_PIE_CFG = Path(__file__).parent / "fixtures" / "pie.test.yaml"
os.environ.setdefault("PIE_CONFIG_FILE", str(_PIE_CFG))

from fastapi.testclient import TestClient  # noqa: E402
from nota_api.main import app              # noqa: E402
```

Le fichier `tests/fixtures/pie.test.yaml` reprend le YAML de dev (`NO-VERIFIER`, mêmes
patterns) et est versionné avec les tests. Un `tmp_path` ne convient pas ici puisqu'il
faut le chemin avant toute fixture.

### Cas à couvrir

```python
def test_route_publique_sans_token(client):
    assert client.get("/health").status_code == 200


def test_route_protegee_sans_token(client):
    # get_token leve PIETokenError -> le middleware renvoie 400
    assert client.get("/documents").status_code == 400


def test_route_protegee_role_insuffisant(client):
    r = client.get("/users", headers={"Authorization": f"Bearer {fake_token(['OPERATOR'])}"})
    assert r.status_code == 403  # /users est reserve a ADMIN


def test_route_protegee_role_ok(client, user_en_base):
    r = client.get("/users", headers={"Authorization": f"Bearer {fake_token(['ADMIN'])}"})
    assert r.status_code == 200


def test_matricule_inconnu_en_base(client):
    token = fake_token(["ADMIN"], matricule="MAT-INEXISTANT")
    r = client.get("/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_organisation_vient_de_la_base_pas_du_token(client, user_en_base):
    # user_en_base appartient a l'organisation 1 ; le token pretend l'organisation 99.
    # Le UserCaller resultant doit porter 1.
    ...


def test_delete_refuse_aux_non_admin(client, user_en_base):
    r = client.delete("/projects/1", headers={"Authorization": f"Bearer {fake_token(['OPERATOR'])}"})
    assert r.status_code == 403


def test_preflight_cors_non_bloque(client):
    r = client.options("/documents", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
    })
    assert r.status_code == 200  # echoue si exa-pie est monte apres CORS
```

Les deux tests les plus utiles de la liste sont le préflight CORS (il verrouille une
décision d'ordonnancement invisible à la lecture) et
`test_organisation_vient_de_la_base_pas_du_token` (il verrouille la frontière de confiance).

---

## 13. Hypothèses à confirmer

Ces points n'ont pas pu être vérifiés sans le code source d'`exa_pie/client.py`. Ils
n'empêchent pas d'avancer, mais il faut les valider au premier test d'intégration.

| Hypothèse | Comment vérifier |
|-----------|------------------|
| `verify()` renvoie `401` sur token invalide et `403` sur rôle insuffisant | Lancer en `NO-VERIFIER` + `log-level: DEBUG`, appeler avec un mauvais rôle, lire le status |
| `get_user_roles()` lit `realm_access.roles` en mode `KEYCLOAK` | Logger le retour de `get_user_roles()` sur un vrai token |
| Le matricule est dans `preferred_username` | Logger les claims complets de `get_context()` sur un vrai token |
| `get_token()` attend `Authorization: Bearer <jwt>` | Lire `exa_pie/utils.py` |

Le plus rapide pour tout lever d'un coup : monter l'API en `NO-VERIFIER` avec
`log-level: DEBUG`, appeler une route protégée avec un vrai token de recette, et lire les
claims dans les logs.

---

## 14. Checklist de mise en place

- [ ] `exa-pie` installé et ajouté à `pyproject.toml`
- [ ] `conf/pie.yaml` (dev, `NO-VERIFIER`) et `conf/pie.prod.yaml` (`CERT-FILE`) créés
- [ ] `PIE_CONFIG_FILE` ajouté au `.env.template`
- [ ] `tests/fixtures/pie.test.yaml` créé et `PIE_CONFIG_FILE` posé dans `conftest.py`
- [ ] `conf/` livré avec l'application (au moment où le packaging sera défini)
- [ ] Certificat SSO fourni par un secret, jamais versionné
- [ ] Rotation du certificat inscrite dans les procédures d'exploitation
- [ ] `PIEFastAPIMiddleware` ajouté **avant** `CORSMiddleware`, avec le commentaire
- [ ] `/health`, `/docs`, `/openapi.json`, `/static` déclarés publics
- [ ] `/db-check` en `ADMIN`, pas en public
- [ ] `get_caller()` réécrit, `501` supprimé
- [ ] `PIEClient` instancié paresseusement via `@lru_cache`
- [ ] `organisation_id` résolu en base via le matricule
- [ ] `api_disable_jwt_validation` supprimé de `Settings`, du `.env` et du `.env.template`
- [ ] `require_user` / `require_roles` appliqués router par router
- [ ] `internal_auth_enabled=true` en prod
- [ ] Hypothèses de la section 13 confirmées sur un vrai token
- [ ] Tests : 400 sans token, 403 rôle insuffisant, 403 matricule inconnu, préflight CORS
- [ ] Bug `setattr` remonté à l'équipe EXA PYTHON

---

## Liens utiles

| Outil | Url |
|-------|-----|
| Jenkins | https://picvert-intra.example.local/view/EXA/job/EXA/job/EXA-PYTHON/job/Components/job/exa-python-pie/ |
| SonarQube | https://cqual.example.local/sonar/dashboard?id=org.sonarqube%3Aexa-pie |
| Artifactory | https://bdistrib-build.example.local/ui/repos/tree/General/bdf-ldev-python-local/exa-pie/ |

Contact : équipe EXA PYTHON.
