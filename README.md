# NOTA - AnNotation et Tests Automatisés

> **Branche `master`** ne contient pas encore de release stable.
> Le développement actif se trouve sur la branche **`develop`**.

## Accéder au code

```bash
git clone https://scm.sofact.banque-france.fr/smartdoc/nota/nota-back.git
cd nota-back
git checkout develop
```
## Installation

### Développement (uv)

Le développement local utilise **uv**. Voir [env-setup.md](./docs/python-env-setup.md) pour la procédure complète : `uv sync`, configuration `.env`, migrations, seed.

### CI/CD et environnements sans uv (pip uniquement)

Le projet reste installable avec `pip` seul, sans `uv` ni environnement virtuel, via les métadonnées standard de `pyproject.toml`.

```bash
# Avec les dépendances de dev (tests, lint), en mode éditable
pip install --group dev -e .

# Sans les dépendances de dev (image de déploiement / CI)
pip install .
```

Le mode éditable (`-e .`) est nécessaire en local pour que la couverture de tests (`pytest --cov`) pointe vers `src/` plutôt que vers une copie installée dans `site-packages`.


## Branches

| Branche | Rôle |
|---|---|
| `main` | Releases stables uniquement |
| `develop` | **Développement actif** |
| `feature/*` | Nouvelles fonctionnalités |
| `fix/*` | Corrections de bugs |

## Contact

Architecte/Développeur - daniel.ferreiralara@banque-france.fr

Développeur - lucas.teyssier@banque-france.fr