# field_spec cote NOTA : ce qui manque, et ce qu'il ne faut PAS faire

## Ne pas copier le modele d'ADAM par-dessus le votre

Une version precedente de cette note disait de remplacer
src/nota_core/models/field_spec.py par celui d'ADAM. C'etait faux, et les
fichiers ont ete retires de cet export.

Les deux modeles ont diverge dans les DEUX sens :

    NOTA a une colonne `description` qu'ADAM n'a pas.
    NOTA nomme la sensibilite `sensitive` ; ADAM la nomme `is_sensitive`.

Ecraser le fichier supprime donc `description` et casse tout ce qui lit
`sensitive` — c'est exactement ce qui s'est produit :

    AttributeError: 'FieldSpec' has no attribute 'sensitive'; maybe 'is_sensitive'?

Annuler : git checkout -- src/nota_core/models/field_spec.py

## Le seul vrai ecart

La colonne de sensibilite existe des deux cotes, sous deux noms. Le test
test_field_spec_porte_la_sensibilite attend `is_sensitive`, comme ADAM.

Renommer dans NOTA, en touchant le modele ET ses lecteurs — les reperer
d'abord, le champ est lu par les schemas de reponse et les routers :

    grep -rn "sensitive" src/ tests/

`description`, elle, ne bouge pas : c'est une colonne propre a NOTA, ADAM
n'a rien a y redire.

## Ce qui reste vrai de la note precedente

La base ne se met pas a jour toute seule. `alembic current` ne rend rien
cote NOTA : le schema y a ete bati par `create_tables()` depuis les modeles.
Or `Base.metadata.create_all` cree les tables absentes mais n'ALTERE jamais
une table existante, et le `--reset` du seed fait un TRUNCATE, pas un DROP.
Un renommage de colonne dans le modele n'atteindra donc la base qu'apres un
DROP SCHEMA public CASCADE; CREATE SCHEMA public; — qui detruit toutes les
donnees, a ne lancer que sur un poste de developpement.

A noter tout de meme : les tests unitaires de routers bouchonnent
entierement la base (AsyncMock sur get_db) et test_recipe_models inspecte
la classe. Aucun des deux ne touche Postgres. Le DROP n'est necessaire que
pour le seed et l'execution reelle, pas pour faire passer la suite.

## Une fois la colonne renommee des deux cotes

La ligne retiree en contournement peut revenir dans scripts/seed.py et
scripts/seed_schema_cerfa.py, dans la construction de FieldSpec, apres
`required=` :

    is_sensitive=spec["is_sensitive"],

build_specs() calcule deja la valeur.
