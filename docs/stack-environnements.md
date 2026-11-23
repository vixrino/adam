# C01 - Stack et Environnements

**Sommaire**

* Stack technique (backend, frontend, traitement des images, infrastructure)
* Vue d'ensemble des environnements
* Environnement DEV : VM Windows
* Environnement STAGING : serveur Linux
* Environnement PROD (à définir)
* Remplacer les services externes en DEV (mocks)
* Passage de DEV à STAGING

> Les environnements permettent de valider NOTA étape par étape avant le STAGING. Trois principes :
>
> 1. **Isolation des risques** : un problème en DEV ne peut pas atteindre le STAGING.
> 2. **Réplicabilité** : le STAGING est identique à la future PROD. Ce qui fonctionne en STAGING avec des CERFA anonymisés fonctionnera en PROD.
> 3. **Sécurité des données** : les données CERFA réelles ne touchent jamais le DEV. Le STAGING utilise uniquement des CERFA anonymisés.

---

## Stack technique

### Backend

| Composant | Technologie |
| --- | --- |
| Langage | Python 3.12 |
| Framework API | FastAPI, avec le middleware d'authentification exa-pie |
| Accès à la base et migrations | SQLAlchemy (asynchrone) + Alembic |
| Base de données | PostgreSQL |
| Stockage des fichiers | PVC (Persistent Volume Claim) : PDF reçus, images des pages |
| Traitements en arrière-plan | 5 workers : images des pages, préremplissage par l'IA, suivi de l'avancement, consensus, tests de qualité |
| Lancement | Une seule commande lance l'API et tous les workers |
| Lecture des formulaires (OCR) | Mistral : `mistral-ocr-latest` lit la page, `mistral-medium-latest` range les valeurs dans les champs |
| Rendu des PDF | PyMuPDF : pages en images PNG à 300 DPI, rapport PDF des tests |
| Authentification | FBI via SMARTDOC (INT/PROD uniquement) : le matricule est lu dans le jeton |
| Annuaire | Active Directory (LDAP), pour affecter une personne à un projet avant sa première connexion |
| Journalisation | exa-logger (format JSON) |
| Gestion des dépendances | uv |
| Qualité du code | pytest (tests), mypy (typage), pylint, black et isort (mise en forme), bandit (sécurité) |

### Frontend

| Composant | Technologie |
| --- | --- |
| Framework | Angular (starter kit Banque de France) |
| Langage | TypeScript |
| Affichage des pages | Images des pages affichées dans un canvas |

### Traitement des images et caviardage

| Composant | Technologie | Rôle | État |
| --- | --- | --- | --- |
| Rendu des pages | PyMuPDF | Transforme chaque page du PDF en image PNG à 300 DPI | En place |
| Remise en ordre | PyMuPDF + Mistral | Reconnaît chaque page du CERFA et reconstruit le PDF dans l'ordre du formulaire | En place |
| Caviardage | DocTR | Repère les zones sensibles (IBAN, NIR, MSA, tolérance zéro) | Prévu |
| Prétraitement | Pillow + OpenCV | Niveaux de gris, redressement, filtre gaussien | Prévu |

### Infrastructure

| Composant | Technologie |
| --- | --- |
| Conteneurisation DEV | Docker Compose (cible) |
| Orchestration STAGING et PROD | Kubernetes, Cloud Catalyse |
| CI/CD | GitLab CI vers OpenShift (responsabilité DevOps) |
| Secrets | Vault Kubernetes |
| Analyse des dépendances | Xray (vulnérabilités connues) |

---

## Vue d'ensemble des environnements

| Paramètre | DEV | RECETTE | INTÉGRATION (STAGING) | PROD |
| --- | --- | --- | --- | --- |
| Infrastructure | VM Windows (Stecad) | À définir | Serveur Linux, Cloud Catalyse | Serveur Linux, Cloud Catalyse (NS NOTA) |
| Conteneurisation | Docker Compose (cible) | À définir | Kubernetes | Kubernetes |
| OCR | Mock local ou Mistral en mode test | À définir | PULSAR ou Mistral en mode test | PULSAR ou Mistral |
| Authentification | Locale (validation du jeton désactivée) | À définir | FBI test via SMARTDOC | FBI via SMARTDOC |
| Données CERFA | Réelles caviardées | À définir | Réelles anonymisées | Réelles |
| Niveau de journal | DEBUG | À définir | INFO | INFO |
| Swagger /docs | Activé | À définir | Lecture seule | Désactivé |
| Accès | Développeurs | À définir | MOE + MOA | Équipe d'exploitation |

---

## Environnement DEV : VM Windows

| Paramètre | Valeur |
| --- | --- |
| Machine | VM Windows |
| Installation | `uv sync --all-extras`, puis lancement de l'API et des workers en une commande |
| Conteneurisation | Docker Compose (cible) |
| PostgreSQL | Instance locale |
| PVC | Répertoire local monté (`PVC_MOUNT_PATH`) |
| OCR | Mock local, ou Mistral en mode test (accès par le proxy, certificat dans `MISTRAL_CA_BUNDLE`) |
| Secrets | Fichier `.env` local, jamais de secrets STAGING ou PROD |
| Authentification | Désactivée : l'appelant est le matricule de `API_DEV_MATRICULE` |
| Journal | DEBUG |
| Swagger /docs | Activé |

> **ATTENTION** : les variables de mock ne doivent JAMAIS se retrouver en STAGING ou en PROD.

---

## Environnement STAGING : serveur Linux

| Paramètre | Valeur |
| --- | --- |
| Infrastructure | Serveur Linux, Cloud Catalyse, namespace Kubernetes dédié |
| PostgreSQL | À confirmer selon la capacité du serveur (cf. H-06) |
| PVC | Persistent Volume Claim Kubernetes |
| OCR | PULSAR ou Mistral en mode test |
| Données CERFA | Réelles anonymisées, données personnelles remplacées |
| Secrets | Vault Kubernetes, même structure qu'en PROD |
| Authentification | FBI test via SMARTDOC |
| Journal | INFO |

> **ATTENTION (H-03, R-05)** : le serveur Linux d'intégration n'est pas encore confirmé. Son provisionnement conditionne le jalon J5.

---

## Environnement PROD (à définir)

*NOTA ne sera pas mis en production dans le cadre de la V1. La cible de déploiement final sera définie après la recette V1.*

Principes déjà arrêtés pour une future PROD :

| Principe | Décision |
| --- | --- |
| Authentification | FBI via SMARTDOC |
| Données | CERFA réels, accès restreint |
| Swagger /docs | Désactivé |
| Journal | INFO, jamais DEBUG |
| Déploiement | Manuel, avec approbation |
| Accès développeur | Aucun accès direct |

---

## Remplacer les services externes en DEV (mocks)

*En DEV, certains services externes ne sont pas accessibles. Ils sont remplacés par des mocks :*

| Service | Remplacement | Variable |
| --- | --- | --- |
| OCR (PULSAR ou Mistral) | Réponse simulée, conforme au contrat d'interface | `OCR_MOCK_ENABLED=true` |
| Authentification | Validation du jeton désactivée, appelant fixé | `API_DISABLE_JWT_VALIDATION=true` et `API_DEV_MATRICULE` |
| Annuaire (Active Directory) | Recherche désactivée | `AD_ENABLED=false` |
| Appels des workers vers l'API | Clé interne désactivée | `INTERNAL_AUTH_ENABLED=false` |

---

## Passage de DEV à STAGING

| Critère | Type | Obligatoire |
| --- | --- | --- |
| Tests unitaires passants, couverture ≥ 80 % | Automatique | OUI |
| Analyse du code (pylint) et typage (mypy) sans erreur | Automatique | OUI |
| Mise en forme vérifiée (black, isort) | Automatique | OUI |
| Analyse de sécurité (bandit, Xray) : 0 vulnérabilité critique | Automatique | OUI |
| Migrations de base à jour et rejouables (Alembic) | Automatique | OUI |
| Aucune variable de mock dans la configuration STAGING | Automatique | OUI |
| Merge Request approuvée | Manuel | OUI |

---

## Changements par rapport à la version précédente

* **Backend.** Ajout des workers et de la commande unique de lancement, de Mistral et de ses deux modèles, de PyMuPDF, de l'annuaire Active Directory, de uv et des outils de qualité. « UFS Middleware » est remplacé par exa-pie, et « EXA Python Logging » par exa-logger.
* **Traitement des images.** Une colonne « État » est ajoutée. Le rendu des pages et leur remise en ordre sont en place. Le caviardage (DocTR) et le prétraitement (Pillow, OpenCV) ne sont pas encore développés.
* **Mocks.** La variable OCR s'appelle `OCR_MOCK_ENABLED` dans le code, et non `OCR_MOCK_MODE`. Ajout de `API_DEV_MATRICULE`, `AD_ENABLED` et `INTERNAL_AUTH_ENABLED`.
* **Passage en STAGING.** Ajout de la mise en forme, de Xray et des migrations.
* **Incohérences corrigées.** L'authentification du STAGING était « Désactivée » dans son tableau, mais « FBI test » dans la vue d'ensemble : la vue d'ensemble est retenue. Les données d'intégration étaient « Réelles » dans la vue d'ensemble, mais « anonymisées » dans le tableau STAGING : « anonymisées » est retenu, conformément au principe 3. La date du jalon J5 (15 juillet 2026, dépassée) est retirée.
* **RECETTE.** Les cases vides sont remplies par « À définir ».
