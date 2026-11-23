# README - Frontend NOTA

Le frontend de NOTA est l'interface web utilisée par les agents : gérer les projets et les lots de documents, définir la liste des champs d'un formulaire, et vérifier les valeurs lues par l'IA, page par page.

**Sommaire**

* Ce que fait le frontend
* Technologies
* Organisation du code
* Installer le projet
* Lancer le projet en local
* Authentification et configuration
* Vérifier le code avant de pousser
* Modèles de l'API
* Points ouverts

---

## Ce que fait le frontend

| Écran | Adresse | Rôle |
| --- | --- | --- |
| Projets | `/projects` | Liste des projets de l'agent ; création, modification, gestion des membres |
| Lots de documents | `/projects/:id/datasets` | Lots d'un projet ; création, ajout de documents |
| Documents | `.../datasets/:id/documents` | Documents d'un lot et leur avancement |
| Vérification | `.../documents/:id` | Écran principal de l'opérateur (voir ci-dessous) |
| Éditeur de schéma | `/projects/:id/schemas/new` ou `/:schemaId` | Liste des champs du formulaire : pages, rubriques, types |
| Pages annexes | `/help`, `/accessibility`, `/sitemap`, `/403`, `/404` | Aide, accessibilité, plan du site, erreurs |

**L'écran de vérification** a trois panneaux :

1. à gauche, les pages et les rubriques du formulaire ;
2. au centre, l'image de la page, avec la zone de chaque champ ;
3. à droite, la liste des champs, avec la valeur proposée par l'IA.

L'opérateur valide ou corrige chaque valeur. Ses réponses partent sous forme de **propositions** liées à sa tâche ; c'est le backend qui retient la valeur finale par consensus.

---

## Technologies

| Composant | Technologie |
| --- | --- |
| Framework | Angular 20 (composants *standalone*) |
| Langage | TypeScript 5.9 |
| État de l'interface | Signals ; RxJS uniquement pour les appels HTTP |
| Design system | `@bdf/design-system` (Banque de France) |
| Authentification | PIE (`pie-core`, `pie-angular`), SSO Banque de France |
| Modèles de l'API | Générés depuis l'OpenAPI du backend (`ng-openapi-gen`) |
| Tests | Jest 30 |
| Qualité | ESLint (Angular), Prettier, `npm audit`, SonarQube |

---

## Organisation du code

Tous les chemins sont sous `src/app/`.

| Couche | Dossier | Rôle |
| --- | --- | --- |
| Pages | `pages/` | Un composant par écran, chargé à la demande ; il porte l'état de l'écran et appelle les services |
| Fonctionnalités | `features/labelling/`, `features/workspace/`, `features/system/` | Composants d'affichage et services HTTP de chaque domaine |
| Partagé | `shared/components/` | Blocs réutilisables : mise en page à trois panneaux, visionneuse de page, fenêtres (popins), listes |
| Cœur | `core/` | Services uniques (HTTP, session, PIE), intercepteurs, modèles générés de l'API (`core/api`) |

Les styles communs sont dans `styles/`, rangés du plus général au plus précis : variables, mixins, reset, balises, mise en page, composants, utilitaires.

---

## Installer le projet

**Prérequis :** Node.js et npm, accès au registre npm interne (design system et paquets PIE).

```bash
npm install
cp src/environments/environment.template.ts src/environments/environment.ts
```

`environment.ts` n'est pas versionné : chacun garde le sien.

---

## Lancer le projet en local

1. **Démarrer le backend** en mode DEV, avec dans son `.env` :
   * `API_DISABLE_JWT_VALIDATION=true` ;
   * `API_DEV_MATRICULE=<un matricule présent dans la table user>` ;
   * `API_CORS_ORIGINS` qui contient `https://localhost:4200`.
2. **Régler `src/environments/environment.ts`** :
   * `auth.enabled: false` (PIE désactivé) ;
   * `devMatricule` : le même matricule que le backend ;
   * `backUrl` : l'adresse du backend, par exemple `http://localhost:8000`.
3. **Lancer le frontend :**

```bash
npm start      # https://localhost:4200
```

Le projet Angular s'appelle `nota-front` dans `angular.json`. Ce nom ne doit pas changer : les scripts et la configuration SonarQube l'utilisent.

---

## Authentification et configuration

* **Au démarrage**, l'application initialise PIE, puis appelle `GET /users/me`. Ce premier appel crée l'agent dans le backend s'il n'existe pas encore. C'est pourquoi il passe avant tout le reste : sinon, un nouvel agent recevrait une erreur 403.
* **En DEV**, avec `auth.enabled: false`, PIE n'est pas appelé. Chaque requête envoie l'en-tête `X-Dev-Matricule`, que le backend n'accepte qu'en DEV.
* **En INTÉGRATION et en PROD**, une seule version compilée sert tous les environnements. Les réglages sont lus au chargement de la page, dans `src/assets/jack-front.js` (`window.smartdoc`) : `backUrl`, `authServerUrl`, `redirectUri`, `resource`, `scope`… Le fichier du dépôt ne contient que des valeurs d'exemple. Les vraies valeurs sont posées au déploiement.

**Gestion des erreurs :**

* coupure réseau ou erreur serveur (5xx) : un seul message global ;
* erreur de saisie (4xx) : message à l'endroit concerné ;
* accès refusé (403) : redirection vers la page `/403`.

---

## Vérifier le code avant de pousser

```bash
npm run verify     # formatage, analyse, tests et audit, à la suite
npm run build      # compilation
```

| Commande | Vérifie |
| --- | --- |
| `npm run format` | Mise en forme Prettier (lignes de 120 caractères, guillemets simples) |
| `npm run lint` | Analyse ESLint |
| `npm test -- --watch=false` | Tests Jest, avec couverture |
| `npm run audit` | Aucune vulnérabilité haute dans les dépendances |
| `npm run build` | L'application compile |

Sous Windows, `scripts/run_checks.ps1` enchaîne les cinq contrôles. Les tests ont besoin d'un `src/environments/environment.ts` : copier le modèle tel quel suffit.

---

## Modèles de l'API

* Les modèles de `core/api/models` sont **générés** à partir de l'OpenAPI du backend (`/openapi.json`, configuration dans `ng-openapi-gen.json`). Ils ne se modifient pas à la main, sauf exception ci-dessous.
* Les services qui appellent l'API sont écrits à la main et restent simples.
* Quand le frontend a besoin d'un champ que le backend n'a pas encore, le modèle est complété en avance. Le contrat attendu est alors décrit dans un fichier `*_BACKEND_TODO.md` à la racine.

---

## Points ouverts

* **Contrats en attente du backend :** les fichiers `*_BACKEND_TODO.md` à la racine (dates des lots, statistiques des documents, `value_type` modifiable sur un champ, `platform_role` dans la liste des utilisateurs).
* **Écran de vérification :** la suppression d'une zone dessinée n'est pas encore faite.
* **Mise en production :** la liste de contrôle de l'authentification reste à terminer (`backUrl` vide, valeur par défaut d'`authMock`, `scope` à plusieurs valeurs).
