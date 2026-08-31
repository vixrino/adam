h2. CONTEXTE

require_user et require_service sont definies mais referencees par aucun router.
Le middleware exa-pie referme l'acces globalement, au seul niveau de l'URL : il
ne distingue pas la methode HTTP ni l'appartenance au projet.

h2. Details

Appliquer les dependances router par router, et introduire require_roles pour le
controle fin.

h2. Criteres d'acceptation

- CA-1 : chaque router porte la dependance correspondant a son perimetre RACI

- CA-2 : une lecture autorisee n'implique pas une ecriture autorisee

- CA-3 : un test par router verifie le refus attendu

h2. Notes

A traiter avant la suppression de API_DISABLE_JWT_VALIDATION, sinon plus aucun
developpement n'est possible sans mock FBI.
