h2. CONTEXTE

Le RACI confie au Superviseur NOTA les datasets de reference, les recettes de
tests et les rapports. Aucune table ne porte ces notions aujourd'hui.

h2. Details

Creer TEST_RECIPE, TEST_EXECUTION, COMPARISON_RESULT, EVALUATION_REPORT, leurs
modeles SQLAlchemy et la migration Alembic.

Une recette designe un jeu de documents et les valeurs attendues. Une execution
est un passage de cette recette. Un resultat de comparaison porte l'ecart sur un
champ. Un rapport agrege l'execution.

h2. Criteres d'acceptation

- CA-1 : les quatre tables existent, avec leurs contraintes d'unicite et leurs
  index

- CA-2 : la migration cree le schema sur une base existante, et create_all sur
  une base neuve

- CA-3 : le perimetre de filtrage de chaque table est decide explicitement et
  documente dans le modele

- CA-4 : le downgrade de la migration restaure l'etat anterieur

h2. Notes

Decision structurante a prendre en premier : ces tables heritent-elles de
OrganisationScoped ? Une recette de reference n'appartient a personne, mais le
filtrage est fail-closed par defaut. Ne pas heriter est un choix a assumer par
ecrit dans le modele.

La verite terrain existe deja en partie : ocr_value et resolved_value donnent le
taux de correction par champ sans aucune table supplementaire.
