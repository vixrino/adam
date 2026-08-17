# Sécuriser l'API NOTA avec exa-pie

## Table des matières

1. [Présentation d'exa-pie](#1-présentation-dexa-pie)
2. [Situation actuelle de NOTA](#2-situation-actuelle-de-nota)
3. [Décisions prises](#3-décisions-prises)
4. [Installation](#4-installation)
5. [Configuration du fichier pie.yaml](#5-configuration-du-fichier-pieyaml)
6. [Branchement du middleware](#6-branchement-du-middleware)
7. [Récupération du contexte utilisateur](#7-récupération-du-contexte-utilisateur)
8. [Réécriture de get_caller](#8-réécriture-de-get_caller)
9. [Contrôle fin des droits](#9-contrôle-fin-des-droits)
10. [Appels machine](#10-appels-machine)
11. [Limites du connecteur](#11-limites-du-connecteur)
12. [Tests](#12-tests)
13. [Point ouvert sur le claim de matricule](#13-point-ouvert-sur-le-claim-de-matricule)
14. [Checklist de mise en place](#14-checklist-de-mise-en-place)

---

## 1. Présentation d'exa-pie

`exa-pie` est un module Python interne, disponible sur le Pypi Sofact. Son rôle est de
valider le JWT d'un utilisateur et de vérifier qu'il a le droit d'appeler l'URL demandée.
Il ne délivre pas de token et ne remplace pas l'IdP : il se place du côté consommateur.

Deux modes sont proposés selon le fournisseur d'identité utilisé.

| Mode | Fournisseur d'identité |
|------|------------------------|
| `KEYCLOAK` | Keycloak |
| `FBI` | FBI, le SSO interne |

Le mode ne modifie que la façon de lire les rôles dans le token. Le reste du
fonctionnement est identique.

### Les verifiers

La validation de signature d'un JWT nécessite la clé publique de l'IdP. Le `verifier`
indique où exa-pie doit aller la chercher.

| Verifier | Valeur attendue dans `value` |
|----------|------------------------------|
| `NO-VERIFIER` | Aucune. La signature n'est pas vérifiée. Réservé au développement |
| `KEY-VALUE` | La clé publique en clair dans le YAML |
| `KEY-FILE` | Chemin vers un fichier contenant la clé publique |
| `CERT-VALUE` | Le certificat X509 en clair dans le YAML |
| `CERT-FILE` | Chemin vers un fichier `.pem` |
| `CERT-URI` | URL exposant le certificat. Impose de renseigner `ssl-verify` |

### Interface exposée

```python
from exa_pie.client import PIEClient

pie_client = PIEClient()                                   # lit conf/pie.yaml

pie_client.is_public_uri('/health')                         # bool
message, status = pie_client.verify(token, '/documents')    # (str, int)
context = pie_client.get_context(token)                     # claims du token
pie_client.get_user_roles(pie_context=context)              # liste de roles
```

Un middleware est fourni pour chacun des frameworks supportés.

| Classe | Framework |
|--------|-----------|
| `PIEDjangoMiddleware` | Django |
| `PIEFalconMiddleware` | Falcon |
| `PIEFastAPIMiddleware` | FastAPI |

Le middleware FastAPI, défini dans `exa_pie/middleware/fastapi.py`, dérive de
`BaseHTTPMiddleware`. Sur chaque requête il applique le traitement suivant.

1. Si l'URI est publique, la requête passe sans aucun contrôle.
2. Sinon le token est extrait des en-têtes par `get_token`, qui renvoie une erreur 400
   si l'en-tête est absent ou malformé.
3. `verify(token, path)` est appelé. Tout statut différent de 200 est renvoyé tel quel.
4. Le token et le contexte sont attachés à la requête, puis la route est appelée.

---

## 2. Situation actuelle de NOTA

> **Mise à jour du 17/08/2026.** Le raccordement décrit dans ce document est
> désormais implémenté et vérifié contre le mock FBI 2.0.6. Les sections 7, 8 et 13
> ont été corrigées d'après le comportement observé, qui diffère sur trois points
> de ce qui était supposé à la rédaction. Cette section décrit l'état d'avant, qui
> reste utile pour comprendre les décisions prises.

Le fichier `src/nota_api/dependencies/auth.py` contenait le code suivant.

```python
if jwt is not None:
    if settings.api_disable_jwt_validation:
        logger.critical("JWT BYPASS actif ne jamais utiliser en production")
        return UserCaller(matricule="MAT00003", organisation_id=1)
    raise HTTPException(status_code=501, detail="Auth JWT non implementee")
```

Deux comportements étaient donc possibles : un contournement qui renvoyait un utilisateur
codé en dur, ou une erreur 501.

Ce contournement a coûté plus cher que son absence n'aurait coûté. Le `organisation_id=1`
ne correspondait à aucune ligne réelle de la base : le périmètre observé en DEV n'était
celui de personne. Un test manuel du cloisonnement, mené en changeant l'organisation d'un
utilisateur en base, a conclu à tort à une faille du filtrage — alors que le matricule
testé n'atteignait jamais le code. Un `501` franc aurait été moins coûteux qu'un faux
utilisateur silencieux.

Second constat : les dépendances `require_user()` et `require_service()` sont définies
mais ne sont référencées par aucun router. Toutes les routes de NOTA sont donc ouvertes
en l'état. **Ce point reste ouvert** : le middleware referme l'accès globalement, mais le
contrôle fin par route n'est pas encore appliqué (cf. section 9 et checklist).

### Ce qu'exa-pie règle, et ce qu'il ne règle pas

Ces deux constats correspondent à deux problèmes distincts, et il est utile de ne pas les
confondre avant d'entamer l'intégration.

Le premier est l'absence de validation du token. Sa correction suppose nécessairement un
composant capable de vérifier une signature et de lire les claims. exa-pie est le moyen
retenu ici parce qu'il est le standard interne, mais ce n'est pas la seule voie
techniquement envisageable : une validation écrite à la main avec PyJWT, accompagnée de la
récupération de la clé publique, produirait le même résultat. Elle reviendrait toutefois à
réimplémenter le connecteur et à s'écarter de ce que font les autres projets de l'équipe.

Le second est l'ouverture des routes. Sa correction consiste à appliquer les dépendances
sur les routers, ce qui ne dépend pas d'exa-pie sur le principe. En pratique cette
correction reste bloquée par la première : une dépendance appliquée aujourd'hui appellerait
`get_caller()`, qui renvoie 501 dès qu'un JWT est présent.

Le middleware d'exa-pie apporte par ailleurs une réponse partielle au second problème. Il
refuse par défaut toute requête dépourvue de token valide sur les routes non déclarées
publiques, ce qui referme l'accès de façon globale sans intervention sur chaque route. Ce
contrôle s'exerce cependant au seul niveau de l'URL. Il ne se substitue pas aux dépendances
FastAPI, pour trois raisons développées plus loin : il ne distingue pas la méthode HTTP
(section 9), il ignore le cloisonnement par organisation (section 11), et il ne fournit pas
d'objet `UserCaller` typé permettant de déduire `agent_id` de l'appelant (section 8).

exa-pie est donc nécessaire mais pas suffisant. La mise en place suit trois étapes : mettre
en place le connecteur et sa configuration, réécrire `get_caller()`, puis appliquer les
dépendances router par router.

---

## 3. Décisions prises

| Sujet | Décision | Justification |
|-------|----------|---------------|
| Ordre des middlewares | exa-pie déclaré avant `CORSMiddleware` | Starlette place le dernier middleware ajouté en position la plus externe. CORS doit rester externe, sinon exa-pie rejette les préflights `OPTIONS` en 400 |
| Verifier en production | `CERT-FILE`, certificat fourni par un secret | Aucun appel HTTP sortant par requête entrante, et pas de dépendance à la disponibilité du SSO |
| Verifier en développement | `NO-VERIFIER` | Permet de forger un token pour tester les rôles sans monter un Keycloak |
| Nombre de fichiers de configuration | Un fichier par environnement, sélectionné par `PIE_CONFIG_FILE` | Aucun des deux fichiers ne contient de secret, seulement un chemin de certificat. Ils restent versionnables |
| Indicateur `PIE_ENABLED` | Non retenu | Un interrupteur supplémentaire capable de désactiver l'authentification représente un risque en production. La configuration de test suffit |
| `api_disable_jwt_validation` | À supprimer | Devient redondant. `NO-VERIFIER` associé à un token forgé couvre le besoin, sans utilisateur codé en dur |
| `organisation_id` | Résolu en base depuis le matricule | Le token ne doit pas déterminer le cloisonnement des données. `User.organisation_id` fait référence |
| Granularité des droits | exa-pie pour les zones, dépendances FastAPI pour les actions | `uris-by-roles` ne discrimine pas la méthode HTTP |
| Portée des dépendances | Déclarées router par router | Une dépendance globale renverrait 401 sur `/health`, que les sondes appellent sans identifiants |
| Instanciation du `PIEClient` | Paresseuse, via `@lru_cache` | Une instanciation au niveau module exigerait `pie.yaml` dès l'import, ce qui complique la configuration des tests |
| Route `/db-check` | Réservée au rôle ADMIN | Son message d'erreur expose des informations sur la connexion Postgres |
| Appels machine | Aucune action requise | Le worker accède directement à Postgres et ne traverse jamais le middleware |
| Contexte dans les routes | `request.state` avec repli par `getattr` | Contourne une anomalie du middleware décrite en section 7 |

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

Le module est publié sur le Pypi interne Sofact et non sur le Pypi public. L'index
configuré, via `pip.conf` ou `PIP_INDEX_URL`, doit pointer dessus, faute de quoi
l'installation échoue sur un message `No matching distribution found`.

---

## 5. Configuration du fichier pie.yaml

exa-pie recherche le fichier `conf/pie.yaml` à la racine du projet. La variable
d'environnement `PIE_CONFIG_FILE` permet de désigner un autre chemin absolu.

### Options disponibles

| Option | Obligatoire | Défaut | Description |
|--------|-------------|--------|-------------|
| `pie.security.mode` | Oui | | `FBI` ou `KEYCLOAK` |
| `pie.security.verifier` | Oui | | Voir le tableau des verifiers |
| `pie.security.value` | Oui | | Dépend du verifier retenu |
| `pie.security.algorithms` | Oui | | Algorithmes de décodage, par exemple `RS256` |
| `pie.security.log-level` | Non | `INFO` | Niveau de log du connecteur |
| `pie.security.ssl-verify` | Non | `False` | Bundle de certificats utilisé par le verifier `CERT-URI` |
| `pie.security.public-uris` | Non | | Patterns REGEX des URI accessibles sans authentification |
| `pie.security.uris-by-roles` | Non | | Association entre patterns REGEX et rôles autorisés |

Trois règles régissent la résolution des patterns.

1. Les patterns sont évalués dans leur ordre de déclaration. Le premier qui correspond
   l'emporte et les suivants ne sont pas testés.
2. Une route qui ne correspond ni à `public-uris` ni à `uris-by-roles` reste accessible,
   mais uniquement avec un token valide, sans contrôle de rôle.
3. En l'absence de token, la requête est rejetée.

L'ordre de déclaration a donc une portée fonctionnelle. Le pattern
`^\/?documents(.*)?$` placé avant `^\/?documents\/admin(.*)?$` rend le second
inatteignable.

### Configuration de développement

Les rôles reprennent l'énumération `UserRole` définie dans `nota_core/enums/roles.py`,
soit `OPERATOR`, `SUPERVISOR` et `ADMIN`.

```yaml
---
pie:
  security:
    mode: KEYCLOAK
    verifier: NO-VERIFIER
    algorithms:
      - RS256
    log-level: DEBUG

    # Routes techniques, ni token ni role.
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

Les routes `/docs` et `/openapi.json` doivent rester publiques. Le navigateur charge
`/openapi.json` depuis la page Swagger sans en-tête `Authorization`, la documentation
s'afficherait vide dans le cas contraire.

`/static` est déclaré par anticipation. Le répertoire `nota_api/static/` contient
`swagger-ui-bundle.js` et `swagger-ui.css`, et `main.py` monte bien `/static`, mais aucun
`docs_url` ni `swagger_ui_parameters` ne les utilise. La route `/docs` sert donc
aujourd'hui la page FastAPI par défaut, qui charge ses ressources depuis un CDN. Le jour
où le Swagger hors ligne sera câblé, ce qui semble être l'intention derrière ces fichiers,
`/static` devra être public.

`/db-check` est protégée par le rôle ADMIN plutôt que déclarée publique, y compris en
développement, de façon que le comportement soit identique dans les deux environnements.

### Configuration de production

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
      # identique au developpement
```

`CERT-FILE` est préféré à `CERT-URI` pour deux raisons. Il évite un appel HTTP sortant sur
le chemin critique de chaque requête, et l'API reste disponible si le point d'accès au
certificat du SSO ne répond plus. En contrepartie, le fichier devra être renouvelé à
l'expiration du certificat, ce qui doit figurer dans les procédures d'exploitation.

Le chemin `/etc/nota/pie/sso.pem` est une proposition. Le dépôt ne contient à ce jour ni
`Dockerfile`, ni fichier `docker-compose`, ni manifeste Kubernetes : le mode de
déploiement n'est pas encore arrêté. Deux exigences restent valables quel que soit le
support retenu. Le certificat doit être fourni par un secret et ne jamais être versionné,
et le fichier `pie.yaml` doit pointer sur son chemin de montage.

La sélection du fichier se fait par variable d'environnement.

```ini
PIE_CONFIG_FILE=/app/conf/pie.prod.yaml
```

À ajouter au `.env.template` :

```ini
# Chemin absolu du fichier de configuration exa-pie (defaut : conf/pie.yaml)
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
# (depourvus d'en-tete Authorization) en 400 et le front ne peut plus appeler l'API.
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

### Justification de l'ordre

Starlette insère chaque middleware en tête de pile. Le dernier `add_middleware` appelé se
retrouve donc en position la plus externe et traite la requête en premier.

Si exa-pie est déclaré après CORS, il devient externe et intercepte les requêtes `OPTIONS`
de préflight, qui ne portent jamais d'en-tête `Authorization`. Il les rejette en 400 avant
que CORS ait pu y répondre. Le front ne parvient alors plus à appeler l'API, et la console
du navigateur n'affiche qu'une erreur CORS générique qui ne renseigne pas sur la cause
réelle.

Comme `uris-by-roles` ne permet pas de filtrer sur la méthode HTTP, il n'est pas possible
d'exclure les requêtes `OPTIONS` par la configuration. L'ordre des middlewares constitue
le seul levier disponible. C'est la raison du commentaire dans le code : cette contrainte
n'est pas visible à la lecture et un remaniement ultérieur pourrait la casser sans s'en
apercevoir. Le test de préflight décrit en section 12 sécurise ce comportement.

### Instanciation au démarrage

La méthode `PIEFastAPIMiddleware.__init__` exécute `self.pie_client = PIEClient()`. La
configuration est donc lue au montage de l'application et non à la première requête. Si le
fichier `pie.yaml` est absent ou invalide, l'application ne démarre pas. Ce comportement
est souhaitable, mais il implique que le fichier soit livré avec l'application et
disponible dans l'environnement de test. C'est ce qui conditionne la fixture décrite en
section 12.

---

## 7. Récupération du contexte utilisateur

Le middleware attache deux informations à la requête : `pie_token`, le JWT brut, et
`pie_context`, les claims décodés.

```python
from fastapi import APIRouter, Request

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("")
async def list_documents(request: Request):
    context = request.state.pie_context
    token = request.state.pie_token
    ...
```

En pratique, la dépendance `require_user` présentée en section 8 est préférable puisqu'elle
renvoie un objet typé. La lecture directe de `request.state` ne sert que pour accéder aux
claims bruts.

### Accès par request.state

Sous Django l'information est disponible sur `request.pie_context`, et sous Falcon sur
`req.pie_context`. Sous FastAPI il faut passer par `request.state`.

L'explication tient au fonctionnement de `BaseHTTPMiddleware` : l'objet `Request` manipulé
par le middleware et celui injecté dans la route sont deux instances distinctes,
reconstruites à partir du même `scope` ASGI. Seul `request.state`, stocké dans
`scope['state']`, est partagé entre les deux.

Or le middleware procède actuellement ainsi :

```python
setattr(request, 'pie_token', token)
setattr(request, 'pie_context', self.pie_client.get_context(token))
```

Les attributs sont posés sur l'instance du middleware, qui est abandonnée juste après. La
route ne les voit donc jamais. Le correctif à remonter à l'équipe EXA PYTHON consiste à
écrire :

```python
request.state.pie_token = token
request.state.pie_context = self.pie_client.get_context(token)
```

### Anomalie confirmée sur le terrain

**Vérifié le 17/08/2026 contre le mock FBI 2.0.6.** Ce n'est plus une hypothèse de lecture
de code : toute requête portant un token valide échouait sur « Contexte d'authentification
indisponible », `pie_context` et `pie_token` étant tous deux absents de la requête reçue
par la dépendance. Le diagnostic de cette section était exact.

Deux précisions par rapport à ce qui était écrit ci-dessus. La route ne lève pas
d'`AttributeError` mais renvoie `None` si l'on interroge l'attribut avec `getattr`, ce qui
rend l'anomalie **silencieuse** — c'est ce qui la rend coûteuse à diagnostiquer. Et les
attributs sont posés directement sur l'objet, pas sur `request.state` : `getattr(request,
"pie_context", None)` est donc la bonne lecture à tenter, `request.state.pie_context`
n'ayant jamais aucune chance d'aboutir tant que le connecteur n'est pas corrigé.

### La source retenue : l'en-tête Authorization

NOTA ne dépend donc pas du middleware pour obtenir le contexte. `claims_from_request()`
essaie trois sources dans l'ordre :

1. `getattr(request, "pie_context", None)`, si c'est un mapping non vide
2. `getattr(request, "pie_token", None)`, dont la charge utile est décodée
3. **l'en-tête `Authorization`**, relu directement — en pratique la seule qui serve

Les deux premières coûtent deux `getattr` et sont conservées : le jour où le connecteur
passera par le scope, le code n'aura pas à évoluer.

Relire l'en-tête ne contourne pas la validation. Cette fonction n'est atteinte que si
`verify()` a rendu 200 : sinon le middleware a déjà répondu 400 ou 401, et la dépendance
n'est jamais appelée. La signature est vérifiée en amont, il ne reste qu'à lire ce qu'elle
protège.

Corollaire de sécurité, développé en section 8 : le chemin de contournement DEV ne doit
jamais emprunter cette fonction, aucune signature n'étant vérifiée dans ce mode.

### Cas des routes publiques

Sur une route déclarée dans `public-uris`, le middleware n'attache rien et
`request.state.pie_context` lève une `AttributeError`. Pour une route susceptible d'être
appelée avec ou sans authentification :

```python
context = getattr(request.state, "pie_context", None)
```

---

## 8. Réécriture de get_caller

L'objectif est de conserver l'interface existante, composée de `Caller`, `UserCaller` et
`ServiceCaller`, de façon que les routers n'aient rien à modifier, tout en remplaçant
l'erreur 501 par une lecture effective du token.

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
        # Le repli couvre l'anomalie setattr du middleware (cf. section 7).
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
    """Lit le claim portant le matricule. Son nom depend de l'IdP, pas d'exa-pie."""
    matricule = context.get(settings.pie_matricule_claim)
    if not matricule:
        logger.error(
            "Claim %r absent du token. Claims disponibles : %s",
            settings.pie_matricule_claim,
            sorted(context),
        )
        raise HTTPException(status_code=401, detail="Matricule absent du token")
    return matricule
```

Le nom du claim est déclaré dans `nota_api/core/config.py` :

```python
class Settings(CoreSettings):
    ...
    pie_matricule_claim: str = "preferred_username"
```

Ce nom est configurable parce qu'il n'est pas encore connu et qu'il diffère entre Keycloak
et FBI. Ce point est développé en section 13.

### Ce qui a été implémenté, et en quoi cela diffère

**Mise à jour du 17/08/2026.** Le code ci-dessus est celui de la rédaction. Trois écarts
sont apparus à l'implémentation, tous imposés par le comportement réel.

**1. `Depends(get_db)` est impossible dans `get_caller`.** C'est une dépendance circulaire :
`get_db` dépend de `get_caller` pour connaître l'organisation à poser en session. La
résolution ouvre donc sa propre session **non scopée**, par `get_async_session()` directement.
Ce n'est pas un contournement mais une nécessité — le filtrage dérive du caller, on ne peut
pas l'appliquer pour le résoudre. La requête se borne à lire `user` par matricule, ce qui ne
divulgue rien : l'appelant apprend sa propre organisation.

**2. Le nom du claim est une liste, pas une valeur unique.** Le token du mock porte le
matricule sous quatre noms qui ne s'accordent pas entre eux (section 13). `PRINCIPAL_CLAIMS`
essaie `sub`, `prn`, `user_name` dans cet ordre, plutôt qu'un `pie_matricule_claim` unique.
Un réglage unique serait à recaler à chaque changement de fournisseur ; l'ordre couvre les
trois conventions rencontrées.

**3. `UserCaller` ne porte pas les rôles du token.** Le modèle prévoyait
`roles: list[str]` alimenté par `pie.get_user_roles()`. L'implémentation porte
`platform_role: Optional[str]`, lu **en base**. La raison est structurelle : `ProjectRole`
dépend du projet, notion qu'un token ne peut pas exprimer. Les rôles du token restent
cantonnés au grillage grossier par URI de `pie.yaml`, et le contrôle fin appartient à la
base. Mélanger les deux mettrait la moitié de l'autorisation dans un YAML et l'autre en base.

### Le contournement DEV ne lit pas le token

Point de sécurité absent de la rédaction initiale, et le plus important de cette section.

Quand `API_DISABLE_JWT_VALIDATION=true`, le middleware n'est pas monté : **aucune signature
n'est vérifiée**. Lire le token dans ce mode reviendrait à faire confiance à un JWT fabriqué
à la main. Poser `"sub": "<matricule d'un administrateur NOTA>"` suffirait à obtenir ses
droits, sans mot de passe, sans FBI, depuis n'importe quel client HTTP.

Le contournement endosse donc un matricule fixe, `API_DEV_MATRICULE`, et ignore entièrement
l'en-tête `Authorization`. Un test verrouille ce comportement en présentant un en-tête forgé
et en vérifiant qu'il est ignoré.

Il passe malgré tout par la résolution en base, donc par une ligne réelle. C'est ce qui
corrige le défaut décrit en section 2 : le périmètre observé en DEV est celui d'une vraie
personne, et le cloisonnement redevient testable sans SSO.

### Instanciation paresseuse du client

Une instruction `_pie_client = PIEClient()` placée directement au niveau du module lirait
`pie.yaml` dès l'import. En test, l'appel `monkeypatch.setenv("PIE_CONFIG_FILE", ...)`
intervient au moment de la fixture, donc après la collecte pytest qui a déjà importé le
module. Le client serait construit avec une configuration erronée, ou l'import échouerait
faute de fichier. Le décorateur `@lru_cache` reporte la construction au premier appel tout
en conservant un client unique pour le processus. C'est également l'usage retenu pour
`get_settings()` et `get_core_settings()` ailleurs dans NOTA.

### Nécessité de l'identité de l'appelant

Ce point justifie l'ensemble de la démarche. La route `POST /jobs` reçoit actuellement
l'auteur du travail dans le corps de la requête.

```python
class JobIn(BaseModel):
    dataset_id: int
    document_id: int
    agent_id: int      # l'appelant declare qui a annote
```

`Job.agent_id` est une clé étrangère vers `user.id`, et le service de consensus
(`nota_api/services/consensus.py`) compte les jobs à l'état `SUBMITTED` pour un document
afin de les comparer à `dataset.required_operators`. Le principe retenu veut que plusieurs
opérateurs distincts annotent un même document de façon indépendante avant validation.

Tant que `agent_id` provient du corps de la requête, un appelant peut attribuer une
annotation à un autre opérateur, et le consensus s'appuie sur une donnée déclarative. Le
claim d'identité permet de corriger ce fonctionnement.

```python
@router.post("", response_model=Dict[str, Any], status_code=201)
async def create_job(
    body: JobIn,                                    # sans agent_id
    caller: UserCaller = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    user = await _resolve_user(db, caller.matricule)
    row = Job(**body.model_dump(), agent_id=user.id)
    ...
```

Sans identité de confiance, l'authentification protège l'accès aux routes mais pas
l'intégrité des données qui y transitent.

Remarque annexe, sans lien avec exa-pie : le comptage `submitted_count` ne déduplique pas
par `agent_id`. Un même opérateur qui soumet plusieurs jobs sur un document satisfait donc
`required_operators` à lui seul. L'ajout d'un `distinct` sur `Job.agent_id` semble
nécessaire, mais le sujet mérite d'être confirmé avec la logique métier avant toute
modification.

### Origine de organisation_id

`organisation_id` détermine les données visibles par l'utilisateur. Le faire provenir du
token reviendrait à laisser le périmètre de visibilité dépendre du contenu de ce token. La
colonne `User.organisation_id` fait référence, et le token sert uniquement à établir
l'identité de l'appelant.

Conséquence assumée : un utilisateur authentifié auprès de l'IdP mais absent de la table
`User` reçoit une erreur 403. Un provisionnement explicite dans NOTA reste donc requis.

### Suppression de api_disable_jwt_validation

Le contournement devient inutile. En développement, `NO-VERIFIER` accepte tout token
forgé, ce qui offre le même confort sans utilisateur codé en dur dans le code de
production. Trois modifications sont nécessaires.

1. Retirer `api_disable_jwt_validation` de la classe `Settings` dans
   `nota_api/core/config.py`.
2. Retirer la ligne correspondante du `.env` et du `.env.template`.
3. Supprimer la branche associée dans `get_caller()`, ce qui est déjà le cas dans le code
   ci-dessus.

Le réglage `internal_auth_enabled` conserve en revanche son utilité pour le chemin
service.

---

## 9. Contrôle fin des droits

exa-pie assure le filtrage grossier, c'est-à-dire les zones accessibles à chaque rôle. Le
filtrage fin, qui détermine les actions autorisées sur ces zones, reste porté par des
dépendances FastAPI puisque `uris-by-roles` ne discrimine pas la méthode HTTP.

À ajouter dans `nota_api/dependencies/auth.py` :

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

Utilisation :

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

### Application des dépendances

`require_user` n'est référencé par aucun router à ce jour. La déclaration se fait au
niveau de chaque router.

```python
router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
    dependencies=[Depends(require_user)],
)
```

La formulation `FastAPI(..., dependencies=[Depends(get_caller)])` couvrirait l'ensemble
des routes en une seule instruction, mais elle s'appliquerait aussi aux routes techniques
telles que `/health` et `/docs`, qui ne portent pas de token et renverraient donc une
erreur 401. Or `/health` est précisément le point d'entrée interrogé sans identifiants par
les sondes applicatives et les répartiteurs de charge : le passer en 401 conduirait à
déclarer l'application indisponible alors qu'elle fonctionne. La déclaration router par
router est plus verbeuse mais explicite, et laisse `/health` et `/db-check` en dehors du
dispositif.

---

## 10. Appels machine

Aucune action n'est nécessaire à ce stade.

Le worker, situé dans `nota_worker/`, ne passe pas par l'API. Il ouvre directement une
session Postgres via `nota_core.db.session.get_async_session` et manipule les modèles
SQLAlchemy. Vérification faite, aucune bibliothèque `httpx`, `requests` ou `aiohttp` n'est
utilisée dans `src/` ni dans `scripts/` ; `httpx` n'est présent qu'en dépendance de
développement pour le `TestClient`. Le worker ne traverse donc jamais le middleware et
n'est pas concerné par sa mise en place.

Le chemin d'authentification par `X-Internal-Token` et `require_service` existe dans
`auth.py` mais n'a aucun appelant. Le conserver ne présente pas d'inconvénient, à condition
de savoir qu'il n'est pas exercé et donc pas éprouvé en conditions réelles.

### Si un appelant machine apparaît

Un service appelant l'API avec `X-Internal-Token` serait rejeté en 400 par exa-pie avant
d'atteindre `get_caller()`, le middleware ne lisant que l'en-tête `Authorization`.
L'approche retenue consisterait alors à préfixer les routes machine par `/internal/` et à
les déclarer publiques auprès d'exa-pie, l'authentification restant assurée par
`require_service`.

```yaml
public-uris:
  - ^\/?internal(.*)?$
```

À plus longue échéance, la solution la plus propre reste un compte de service Keycloak en
`client_credentials`, associé à un rôle `SERVICE` déclaré dans `uris-by-roles`. Elle
supprime `X-Internal-Token` et unifie l'authentification sur un mécanisme unique.

---

## 11. Limites du connecteur

### Absence de filtrage par méthode HTTP

Traité en section 9.

### Absence de contrôle sur les ressources

exa-pie ne connaît pas `User.organisation_id`. Un utilisateur ADMIN rattaché à
l'organisation 1 franchit le middleware sur `/documents/42` même si ce document appartient
à l'organisation 2. Le cloisonnement par organisation reste intégralement à la charge de
NOTA, dans les requêtes des routers. Il s'agit du risque le plus probable à l'usage, le
connecteur pouvant donner l'impression d'une couverture plus large qu'elle ne l'est.

### Code synchrone dans un middleware asynchrone

`verify()` et `get_context()` sont des appels bloquants exécutés dans une méthode
`async def dispatch`, à chaque requête. Le choix de `CERT-FILE` écarte le cas le plus
défavorable, celui d'un appel HTTP sortant par requête entrante, mais la vérification de
signature RSA reste dans la boucle d'événements. Une mesure est à prévoir avant la mise en
production. Si l'impact se confirme, l'appel peut être encapsulé dans
`run_in_threadpool`.

### BaseHTTPMiddleware et les réponses en flux

`BaseHTTPMiddleware` présente des limitations connues avec les réponses en streaming. NOTA
servant des fichiers via `/files`, il convient de vérifier si certaines routes utilisent
`StreamingResponse` ou `FileResponse`.

---

## 12. Tests

### Génération d'un token de test

Avec `NO-VERIFIER` la signature n'est pas contrôlée : tout JWT correctement formé est
accepté.

```python
import base64
import json


def fake_token(roles: list[str], matricule: str = "MAT00003") -> str:
    def seg(d: dict) -> str:
        raw = json.dumps(d).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = seg({"alg": "RS256", "typ": "JWT"})
    payload = seg({
        # Meme claim que settings.pie_matricule_claim, sinon les tests valident
        # un format que la production n'utilisera pas.
        settings.pie_matricule_claim: matricule,
        "realm_access": {"roles": roles},
    })
    return f"{header}.{payload}.signature-bidon"
```

### Configuration des tests

Le `PIEClient` du middleware est construit au montage de l'application. Les tests ont donc
besoin d'un `pie.yaml` lisible avant l'import de `nota_api.main`. Une fixture classique
intervient trop tard, l'import ayant lieu à la collecte. La variable doit être posée au
niveau module du `conftest.py`.

```python
# tests/conftest.py, avant tout import de nota_api.
import os
from pathlib import Path

_PIE_CFG = Path(__file__).parent / "fixtures" / "pie.test.yaml"
os.environ.setdefault("PIE_CONFIG_FILE", str(_PIE_CFG))

from fastapi.testclient import TestClient  # noqa: E402
from nota_api.main import app              # noqa: E402
```

Le fichier `tests/fixtures/pie.test.yaml` reprend la configuration de développement, avec
`NO-VERIFIER` et les mêmes patterns, et il est versionné avec les tests. Un répertoire
`tmp_path` ne convient pas puisque le chemin doit être connu avant toute fixture.

### Cas à couvrir

```python
def test_route_publique_sans_token(client):
    assert client.get("/health").status_code == 200


def test_route_protegee_sans_token(client):
    # get_token leve PIETokenError, le middleware renvoie 400
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
    # user_en_base appartient a l'organisation 1, le token pretend l'organisation 99.
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

Deux de ces tests méritent une attention particulière. Le test de préflight sécurise une
décision d'ordonnancement invisible à la lecture du code. Le test
`test_organisation_vient_de_la_base_pas_du_token` sécurise la frontière de confiance entre
le token et la base.

---

## 13. Le claim de matricule — point tranché

**Résolu le 17/08/2026** par décodage d'un token réel du mock FBI 2.0.6.

| Hypothèse | Statut |
|-----------|--------|
| `verify()` renvoie 401 sur token invalide et 403 sur rôle insuffisant | Confirmée |
| `get_user_roles()` lit `realm_access.roles` en mode `KEYCLOAK` | **À revérifier**, cf. ci-dessous |
| `get_token()` attend un en-tête `Authorization: Bearer <jwt>` | Confirmée |
| Le matricule est porté par le claim `preferred_username` | **Infirmée** |

### La réponse : `sub`, et trois autres

`preferred_username` **n'existe pas** dans le token FBI. La charge utile réelle, pour
l'utilisateur `i659418` du mock :

```json
{
  "sub": "I659418",
  "user_name": "I659418",
  "prn": "I659418",
  "uid": "i659418",
  "displayname": "I659418",
  "authorities": ["OPERATOR"],
  "rolesApplicatifs": "OPERATOR",
  "email": "test.operateur@banque-france.fr",
  "iss": "FBI-MOCK-SERVER",
  "oracle.oauth.client_origin_id": "FBI-Appli-Demo"
}
```

Quatre claims portent le matricule, et **ils ne s'accordent pas sur la casse** : `sub`,
`prn` et `user_name` rendent `I659418`, tandis que `uid` rend `i659418`. La comparaison en
base est donc insensible à la casse et aux espaces — un seul token se contredisant
lui-même, rien ne garantit la régularité du vrai FBI.

L'ordre retenu est `sub`, puis `prn`, puis `user_name`. `sub` d'abord parce que c'est le
sujet au sens de la RFC 7519, renseigné par tout émetteur conforme ; `prn` ensuite,
convention Oracle dont le mock imite les claims (`oracle.oauth.*`, `iss: FBI-MOCK-SERVER`) ;
`user_name` en dernier, convention Spring OAuth2. `uid` est écarté : il porte la casse
saisie par l'agent.

### Un point nouveau à vérifier : les rôles en mode KEYCLOAK

`conf/pie.yaml` déclare `mode: KEYCLOAK`, et `get_user_roles()` lit alors `realm_access.roles`.
Or **le token FBI ne contient pas `realm_access`** : il porte `authorities` et
`rolesApplicatifs`.

Deux conséquences possibles, non départagées à ce jour : soit le filtrage `uris-by-roles`
ne s'applique pas du tout, soit il refuse tout. En développement, `NO-VERIFIER` a pu masquer
la question — les deux appels de recette sont passés sur `/projects`, qui exige pourtant un
rôle.

Le test décisif, à mener avant toute mise en production : appeler une URI réservée à `ADMIN`
avec le token d'un `OPERATOR`.

```powershell
Invoke-RestMethod "http://localhost:8001/api/v1/organisations" -Headers @{Authorization="Bearer $op"}
```

Un **403** confirme que le grillage fonctionne. Un `200` signifie que `uris-by-roles` ne
filtre rien, et que `mode: FBI` doit remplacer `mode: KEYCLOAK` dans les deux fichiers de
configuration.

### Pourquoi le nom du claim est introuvable dans le code

`preferred_username` n'apparaît nulle part dans le source d'exa-pie, ce qui est attendu.
La méthode `get_context()` se contente de décoder le JWT et d'en renvoyer la charge utile.
Les noms de claims proviennent de l'IdP qui a émis le token, et non du connecteur. exa-pie
ne nomme explicitement que les claims de rôles, seule information qu'il doit extraire
lui-même. Rechercher le nom du claim de matricule dans le source ne peut donc rien donner,
quel que soit ce nom.

`preferred_username` reste le candidat le plus probable puisqu'il s'agit de la convention
Keycloak et que `pie.yaml` déclare `mode: KEYCLOAK`. Si l'IdP retenu est FBI, ou si le
realm Keycloak a été configuré avec un mapper spécifique, le nom sera différent : `uid`,
`matricule`, `employeeNumber` ou `sub` par exemple.

### Comment trancher

Seule l'inspection d'un token réel permet de conclure. Deux méthodes équivalentes sont
possibles.

1. Décoder hors ligne un token de recette, par exemple avec
   `python -c "import jwt; print(jwt.decode(t, options={'verify_signature': False}))"`,
   et lire la charge utile.
2. S'appuyer sur les logs. La fonction `_extract_matricule()` présentée en section 8
   journalise déjà `sorted(context)` lorsque le claim configuré est absent. Le nom exact
   apparaît donc au premier appel authentifié.

Le nom est déclaré en configuration plutôt qu'en dur pour cette raison précise :
l'intégration peut démarrer sans connaître la réponse, et le jour où elle est établie, la
correction se limite à une ligne dans le `.env` au lieu d'une modification de code.

---

## 14. Checklist de mise en place

*État au 17/08/2026.*

### Fait

1. [x] `exa-pie` installé et déclaré dans `pyproject.toml` (`exa-pie>=1.4.0`)
2. [x] `conf/pie.yaml` et `conf/pie.prod.yaml` créés
3. [x] `PIE_CONFIG_FILE` ajouté au `.env.template`
4. [x] `PIEFastAPIMiddleware` déclaré avant `CORSMiddleware`, commentaire inclus
5. [x] `/health`, `/docs`, `/openapi.json` et `/static` déclarés publics
6. [x] `/db-check` réservée au rôle ADMIN
7. [x] `get_caller()` réécrit, erreur 501 et `UserCaller` codé en dur supprimés
8. [x] `organisation_id` et `platform_role` résolus en base à partir du matricule
9. [x] Claim de matricule identifié : `sub`, avec repli sur `prn` et `user_name`
10. [x] Contournement DEV rendu inoffensif — il ignore le token, test à l'appui
11. [x] Tests : 41 sur la résolution du caller, dont le token forgé en mode bypass
12. [x] Recette de bout en bout contre le mock — sans token 400, `OPERATOR` 1 projet,
    `BUSINESS_ADMIN` 2 projets

### À faire

13. [ ] **Vérifier `uris-by-roles` avec un token FBI** — `mode: KEYCLOAK` lit
    `realm_access.roles`, absent du token FBI (section 13). Bascule éventuelle en
    `mode: FBI`
14. [ ] Anomalie `setattr` remontée à l'équipe EXA PYTHON (section 7)
15. [ ] `require_user` et `require_roles` appliqués router par router
16. [ ] `agent_id` retiré de `JobIn` et déduit de l'appelant authentifié
17. [ ] `tests/fixtures/pie.test.yaml` créé et `PIE_CONFIG_FILE` posé dans `conftest.py`
18. [ ] `PIEClient` instancié paresseusement via `@lru_cache` — non nécessaire en l'état,
    la dépendance n'instancie pas de client, mais le deviendra si `get_user_roles()` est
    utilisé
19. [ ] `conf/` livré avec l'application, une fois le packaging défini
20. [ ] Certificat SSO fourni par un secret, jamais versionné
21. [ ] Renouvellement du certificat inscrit dans les procédures d'exploitation
22. [ ] `internal_auth_enabled` positionné à `true` en production
23. [ ] `api_disable_jwt_validation` supprimé de `Settings`, du `.env` et du `.env.template`
    — **en dernier**, une fois le point 15 traité, sinon plus aucun développement n'est
    possible sans mock FBI

---

## Liens utiles

| Outil | Url |
|-------|-----|
| Jenkins | https://picvert-intra.example.local/view/EXA/job/EXA/job/EXA-PYTHON/job/Components/job/exa-python-pie/ |
| SonarQube | https://cqual.example.local/sonar/dashboard?id=org.sonarqube%3Aexa-pie |
| Artifactory | https://bdistrib-build.example.local/ui/repos/tree/General/bdf-ldev-python-local/exa-pie/ |

Contact : équipe EXA PYTHON.
