# field_spec : ADAM et NOTA ont diverge, et c'est NOTA qui a raison

## Ne pas copier le modele d'ADAM par-dessus celui de NOTA

Une version precedente de cette note disait de remplacer
src/nota_core/models/field_spec.py par celui d'ADAM. C'etait faux, et les
fichiers ont ete retires de l'export.

La MR !34 de NOTA — « Finalisation de la page de schema » — a tranche :

    is_sensitive  ->  sensitive          (renommage assume)
    description                          (colonne ajoutee)

avec la migration 20260912_1803_add_description_sensitive_to_field_spec.
Ecraser le fichier par celui d'ADAM supprime donc `description` et casse
tous les lecteurs de `sensitive` :

    AttributeError: 'FieldSpec' has no attribute 'sensitive'; maybe 'is_sensitive'?

Annuler : git checkout -- src/nota_core/models/field_spec.py

## C'est ADAM qui doit s'aligner, pas l'inverse

NOTA a une migration, un router et des schemas Pydantic qui portent
`sensitive` et `description`. ADAM n'a que `is_sensitive` et pas de
description. Le retard est de ce cote-ci.

Cote NOTA il ne reste donc qu'un test a aligner sur le modele — c'est le
test qui est en retard sur la MR, pas le modele :

    tests/unit/test_recipe_models.py, test_field_spec_porte_la_sensibilite

        - FieldSpec.__table__.c.is_sensitive
        + FieldSpec.__table__.c.sensitive

## Le seed

scripts/seed.py et scripts/seed_schema_cerfa.py ne passent plus du tout la
sensibilite a la construction des FieldSpec : la ligne en avait ete retiree
quand la colonne semblait absente cote NOTA. Elle ne l'etait pas, elle avait
change de nom. La ligne peut revenir, sous le nom de la MR !34, apres
`required=` :

    sensitive=spec["is_sensitive"],

La clef du dict que rend build_specs() garde son nom, elle : c'est une clef
interne au script, pas une colonne.
