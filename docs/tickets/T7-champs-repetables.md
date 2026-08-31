h2. CONTEXTE

group_id distingue les occurrences d'un champ repetable. La fusion le pose,
l'index d'unicite partiel le couvre, mais aucun test ne l'exerce contre une base :
group_id vaut NULL partout dans les jeux existants.

h2. Details

Ajouter un scenario avec un FieldSpec porteur d'un group_id et un OCR rendant
plusieurs occurrences.

h2. Criteres d'acceptation

- CA-1 : n occurrences detectees produisent n DOCUMENT_FIELD distincts

- CA-2 : un second passage n'en cree aucun doublon

- CA-3 : la contrainte d'unicite du triplet est verifiee contre une vraie base

h2. Notes

Le jour ou un formulaire liste trois heritiers, ce comportement sera decouvert en
production.
