# adam_core

Package transverse du projet NOTA. Il contient tous les composants partagés entre les différents services : modèles ORM, configuration, migrations, énumérations et utilitaires.

`adam_core` ne dépend d'aucun autre package NOTA. C'est lui qui est importé par `adam_api`, et potentiellement par tout futur service (`adam_worker`, `nota_cli`, etc.).

---

## Structure

```
adam_core/
├── core/
│   └── config.py         Configuration .env transverse (CoreSettings)
├── db/
│   ├── base.py           DeclarativeBase SQLAlchemy partagée
│   └── session.py        Engine async
├── enums/
│   ├── ocr.py            OcrProvider, StorageMode
│   ├── roles.py          UserRole, ExportFormat
│   └── status.py         DocumentStatus, FieldValueType...
├── migrations/
│   ├── env.py            Configuration Alembic async
│   ├── script.py.mako    Template de migration
│   └── versions/         Fichiers de migration générés
├── models/
│   ├── __init__.py       Import de tous les modèles (requis pour Alembic)
│   ├── organisation.py
│   ├── user.py
│   ├── user_project.py
│   └── ...
├── schemas/              Schémas Pydantic partagés
└── utils/
    ├── volumetry.py      Estimation de volumétrie BDD
    └──...
```
## Configuration

`adam_core` expose `CoreSettings`, une classe `pydantic-settings` qui lit les variables d’environnement depuis un fichier `.env`.

```python
from adam_core.core.config import get_core_settings

settings = get_core_settings()
print(settings.async_database_url)


Les variables lues par `CoreSettings` :

| Variable | Défaut | Description |
|---|---|---|
| `APP_ENV` | `dev` | Environnement : dev, staging, prod |
| `APP_NAME` | `NOTA` | Nom de l'application |
| `APP_VERSION` | `0.1.0` | Version |
| `POSTGRES_USER` | `postgres` | Utilisateur PostgreSQL |
| `POSTGRES_PASSWORD` | `` | Mot de passe PostgreSQL |
| `POSTGRES_HOST` | `localhost` | Hôte PostgreSQL |
| `POSTGRES_PORT` | `5432` | Port PostgreSQL |
| `POSTGRES_DB` | `nota_db` | Nom de la base |
| `LOG_LEVEL` | `DEBUG` | Niveau de log |
| `LOG_FORMAT` | `text` | Format de log : text ou json |

Comme exemple, `adam_api` hérite de `CoreSettings` et y ajoute ses propres variables (CORS, JWT, OCR...).

---

## Migrations Alembic

Les migrations sont gérées par Alembic avec SQLAlchemy en mode async.

### Workflow standard

**1. Modifier un modèle ORM**

Éditer le fichier correspondant dans `models/`. Par exemple ajouter une colonne sur `Document`.

**2. Générer la migration**

```powershell
# dans la racine du projet
python -m alembic -c src/adam_core/alembic.ini revision --autogenerate -m "description du changement"
```

Alembic compare l'état des modèles Python avec l'état réel de la base et génère automatiquement le script de migration dans `migrations/versions/`.

**3. Vérifier le fichier généré**

Toujours ouvrir et lire le fichier généré avant de l'appliquer. Alembic peut manquer certains cas (renommage de colonne, contraintes complexes).

**4. Appliquer la migration**

```powershell
python -m alembic -c src/adam_core/alembic.ini upgrade head
```

### Commandes utiles

```powershell
# Etat actuel de la base
python -m alembic -c src/adam_core/alembic.ini current

# Historique des migrations
python -m alembic -c src/adam_core/alembic.ini history --verbose

# Revenir à la migration précédente
python -m alembic -c src/adam_core/alembic.ini downgrade -1

# Revenir à l'état initial (vide)
python -m alembic -c src/adam_core/alembic.ini downgrade base

# Appliquer toutes les migrations en attente
python -m alembic -c src/adam_core/alembic.ini upgrade head
```

### Règles importantes

- Ne jamais modifier un fichier de migration déjà appliqué en production.
- Toujours vérifier le fichier généré avant `upgrade head`.
- En DEV, si le schéma est cassé : `downgrade base` puis `upgrade head`.
- Le fichier `migrations/versions/__init__.py` ne doit pas exister (Alembic gère ce dossier seul).

---

## Modèles ORM

Les modèles suivent les conventions SQLAlchemy 2.x avec `Mapped` et `mapped_column`.

### Conventions de nommage en base

| Type | Format | Exemple |
|---|---|---|
| Table | snake_case singulier | `document_field` |
| Index | `ix_<table>_<colonne>` | `ix_user_email` |
| Unique | `uq_<table>_<colonnes>` | `uq_field_spec_schema_group_key` |
| FK | `fk_<table>_<colonne>_<table_cible>` | `fk_user_organisation_id_organisation` |
| PK | `pk_<table>` | `pk_document` |
| Check | `ck_<table>_<nom>` | `ck_field_spec_polygon_length` |

### Relations et lazy loading

Toutes les relations sont déclarées avec `lazy="noload"`. Elles ne sont jamais chargées automatiquement, il faut les demander explicitement via `selectinload` ou `db.refresh`.

```python
from sqlalchemy.orm import selectinload

# Charger un dataset avec ses documents
result = await db.execute(
    select(Dataset)
    .where(Dataset.id == 1)
    .options(selectinload(Dataset.documents))
)
dataset = result.scalar_one()
```

---

## Utilitaires

### Volumétrie

```python
from adam_core.utils.volumetry import estimate_row_size, estimate_table_size, format_size

# Taille estimée d'une ligne
size = estimate_row_size(document)
print(format_size(size))  # "1.2 KB"

# Taille estimée d'une table entière
stats = estimate_table_size(documents)
print(stats["total_human"])   # "45.3 MB"
print(stats["avg_human"])     # "512.0 B"
```

Il s'agit d'une estimation basée sur les types PostgreSQL. Pour la taille réelle en base :

```sql
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```