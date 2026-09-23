# Export des modeles field_spec et document_field pour NOTA

Fichiers a copier TELS QUELS (imports deja renommes nota_*) — ne pas retaper :

    nota_core/models/field_spec.py      -> src/nota_core/models/field_spec.py
    nota_core/models/document_field.py  -> src/nota_core/models/document_field.py

Ces deux copies REMPLACENT integralement les versions precedentes cote NOTA.

## Pourquoi

Onze tests echouaient cote NOTA, tous sur la meme cause : field_spec y est
d'une generation anterieure.

    test_field_spec_porte_la_sensibilite    AttributeError: is_sensitive
    9 x test_router_schemas                 409 au lieu de 201 / 200 / 204
    test_ocr_polygon_persisted_and_returned polygon rendu None

Trois manques, pas onze :

1. `field_spec.is_sensitive` n'existe pas. La colonne arbitre le stockage de
   comparison_result — valeurs en clair pour un champ ordinaire, HMAC pour une
   donnee personnelle.

2. La contrainte d'unicite de field_spec ne porte pas group_id. Sans lui, deux
   instances d'une meme section repetable — le pret n° 1 et le pret n° 3 du
   CERFA — entrent en collision, d'ou les 409. La forme correcte est
   UniqueConstraint(schema_id, section_id, group_id, field_key).

3. document_field ne persiste pas ocr_polygon.

## La base ne se met pas a jour toute seule

`alembic current` ne rend rien cote NOTA : aucune migration n'y a jamais ete
appliquee, le schema a ete bati par `create_tables()` depuis les modeles.

Consequence a ne pas manquer : `Base.metadata.create_all` cree les tables
absentes mais n'ALTERE jamais une table existante, et le `--reset` du seed
fait un TRUNCATE, pas un DROP. Copier les modeles ne suffit donc pas : tant
que l'ancienne table field_spec est en base, la colonne n'apparaitra pas et
les 409 resteront.

Il faut supprimer le schema pour que create_tables le rebatisse :

    DROP SCHEMA public CASCADE;
    CREATE SCHEMA public;

ATTENTION : cette commande detruit toutes les donnees de la base. C'est sans
consequence sur un poste de developpement, ou le seed reconstruit tout, et a
ne jamais lancer ailleurs.

## Sequence complete

1. Copier les deux fichiers.
2. DROP SCHEMA public CASCADE; CREATE SCHEMA public;
3. uv run python scripts/seed.py --reset
4. uv run pytest

## Une fois que cela passe

Le seed n'affecte plus is_sensitive a la creation des FieldSpec : c'est un
contournement pose quand la colonne manquait cote NOTA. La colonne existant
des deux cotes, la ligne peut revenir dans scripts/seed.py et dans
scripts/seed_schema_cerfa.py :

    is_sensitive=spec["is_sensitive"],

a remettre dans la construction de FieldSpec, apres `required=`.
build_specs() calcule deja la valeur, rien d'autre a ecrire.
