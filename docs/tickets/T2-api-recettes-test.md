h2. CONTEXTE

Le modele de donnees des recettes existe (T1) mais rien ne permet de les creer ni
de les lancer.

h2. Details

Endpoints CRUD sur TEST_RECIPE, et lancement d'une execution. Reserves au
Superviseur NOTA et a l'Administrateur NOTA.

h2. Criteres d'acceptation

- CA-1 : creer, lire, modifier et supprimer une recette

- CA-2 : POST sur l'execution cree une TEST_EXECUTION en attente et rend son id

- CA-3 : un Operateur Metier ou un Administrateur Metier recoit 403

- CA-4 : les URI sont declarees dans conf/pie.yaml pour le grillage grossier

h2. Notes

Depend de T1.
