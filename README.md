
Empreinte de la verite (nota_core/benchmark/verite.py) :
- l'export garde l'empreinte de la verite de chaque document
  (dataset_export.verite_empreintes), sur les seuls champs verifies ;
- le worker la recalcule, signale les documents corriges depuis l'export
  et note l'empreinte jugee sur l'execution (test_execution.verite_hash) ;
- comparer() rend « verite humaine differente » quand deux executions
  n'ont pas juge la meme verite.
Migration e1f2a3b4c5d6 (colonnes nullables, schema nomme).

Consigne libre (config.ocr.prompt) : 403 pour un non NOTA_ADMIN, a la
creation, au PATCH et a la nouvelle version d'une recette.
