"""
DeclarativeBase partagée par tous les modèles ORM du projet.

Convention de nommage PostgreSQL :
  - tables  : snake_case, singulier (ex : organisation, user_project)
  - index   : ix_<table>_<colonne>
  - unique  : uq_<table>_<colonnes>
  - FK      : fk_<table>_<colonne>
  - PK      : pk_<table>
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Plusieurs applications partagent la meme base, chacune dans son schema.
SCHEMA_NAME = "nota"

# Naming conventions PostgreSQL
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base déclarative unique pour tous les modèles ORM."""

    metadata = MetaData(schema=SCHEMA_NAME, naming_convention=NAMING_CONVENTION)
