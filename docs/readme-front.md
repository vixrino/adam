# NOTA - Notation et Tests Automatisés (frontend)

Interface web de NOTA : gestion des projets et des lots de documents, édition de la liste des champs d'un formulaire, et vérification par les opérateurs des valeurs lues par l'IA.

> La branche `main` ne contient pas encore de release stable. Le développement actif se trouve sur la branche `develop`.

## Accéder au code

```bash
git clone https://scm.sofact.banque-france.fr/smartdoc/nota/nota-front.git
cd nota-front
git checkout develop
```

## Branches

| Branche | Rôle |
| :--- | :--- |
| `main` | Releases stables uniquement |
| `develop` | Développement actif, base de toutes les branches |
| `feature/*` | Nouvelles fonctionnalités, créées depuis `develop` |
| `fix/*` | Corrections de bugs, créées depuis `develop` |

Toute modification passe par une Merge Request vers `develop`.

## Technologies

| Composant | Technologie |
| :--- | :--- |
| Framework | Angular 20 (composants *standalone*) |
| Langage | TypeScript 5.9 |
| État | Signals ; RxJS uniquement pour les appels HTTP |
| Design system | `@bdf/design-system` |
| Authentification | PIE (`pie-core`, `pie-angular`) |
| Tests | Jest 30 |
| Qualité | ESLint, Prettier, `npm audit` |

## Prérequis

* Node.js (version à confirmer)
* npm, avec accès au registre interne (design system et paquets PIE)
* Le backend NOTA lancé en local (voir le README du backend)

## Installation

```bash
npm install
cp src/environments/environment.template.ts src/environments/environment.ts
```

`environment.ts` n'est pas versionné. Pour travailler en local sans SSO, y mettre :

* `auth.enabled: false` ;
* `devMatricule` : un matricule présent dans la table `user` du backend ;
* `backUrl` : l'adresse du backend, par exemple `http://localhost:8000`.

Côté backend, le `.env` doit contenir `API_DISABLE_JWT_VALIDATION=true`, le même `API_DEV_MATRICULE`, et `https://localhost:4200` dans `API_CORS_ORIGINS`.

## Lancer le serveur de développement

```bash
npm start
```

L'application est accessible sur `https://localhost:4200/` (en HTTPS). Elle se recharge automatiquement à chaque modification des fichiers sources.

## Build

```bash
npm run build
```

Les artefacts de build sont générés dans `dist/nota-front`. Une seule version compilée sert tous les environnements : les réglages (`backUrl`, adresses du SSO…) sont lus au chargement dans `src/assets/jack-front.js`, rempli au déploiement.

## Tests

```bash
npm test -- --watch=false
```

> Lance les tests unitaires via Jest, avec la couverture de code. Les tests ont besoin de `src/environments/environment.ts` : copier le modèle tel quel suffit.

## Lint et formatage

```bash
npm run verify
```

> Enchaîne le formatage (Prettier), l'analyse (ESLint), les tests et l'audit des dépendances. Sous Windows, `scripts/run_checks.ps1` fait la même chose, puis lance le build.

## Organisation du code

| Dossier (sous `src/app/`) | Rôle |
| :--- | :--- |
| `pages/` | Un composant par écran : projets, lots, documents, vérification, éditeur de schéma, erreurs |
| `features/` | Composants et services par domaine : `labelling`, `workspace`, `system` |
| `shared/components/` | Blocs réutilisables : mise en page à trois panneaux, visionneuse de page, fenêtres, listes |
| `core/` | Services uniques (HTTP, session, PIE), intercepteurs, modèles de l'API |

Les modèles de `core/api/models` sont générés depuis l'OpenAPI du backend (`ng-openapi-gen.json`) : ne pas les modifier à la main. Quand le backend n'a pas encore un champ attendu, le contrat est décrit dans un fichier `*_BACKEND_TODO.md` à la racine.

## Génération de code

```bash
ng generate component nom-du-composant
```

Autres schématiques disponibles : `directive`, `pipe`, `service`, `guard`, `interface`, `enum`.

## Contact

Développeur - daniel.ferreiralara@banque-france.fr
