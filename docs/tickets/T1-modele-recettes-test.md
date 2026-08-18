h2. CONTEXTE

Le Superviseur NOTA doit evaluer la qualite du moteur OCR : comparer ce que la
machine lit a une verite terrain, et suivre les evaluations dans le temps —
Mistral s'ameliore derriere un identifiant de modele stable.

h2. Details

Creer test_recipe, test_execution, comparison_result, evaluation_report, leurs
modeles SQLAlchemy, la migration Alembic, et la colonne field_spec.is_sensitive.

La verite terrain est designee, pas copiee : une recette fige un perimetre de
documents, la verite reste document_field restreinte aux champs portant une
field_proposal. Les ecarts seuls sont stockes, valeurs en clair pour les champs
non sensibles, HMAC et distance d'edition pour les autres.

h2. Criteres d'acceptation

- CA-1 : les quatre tables existent avec leurs contraintes d'unicite, leurs
  index, et heritent du filtrage par organisation et par projet

- CA-2 : la migration cree le schema sur une base existante, create_all sur une
  base neuve, et le downgrade restaure l'etat anterieur

- CA-3 : le denominateur d'un rapport ne compte que les champs verifies par un
  humain (au moins une field_proposal), jamais les champs auto-valides

- CA-4 : aucune valeur de champ sensible n'est stockee ni loguee ; la politique
  est portee par field_spec.is_sensitive

- CA-5 : la suppression d'un document emporte ses ecarts (CASCADE) sans toucher
  aux agregats publies

h2. Notes

Le consensus copie ocr_value dans resolved_value pour tout champ sans
proposition : compter ces champs mesurerait le moteur contre lui-meme. C'est la
decision structurante du modele.

L'histogramme de confiance est capture sur l'execution : les champs corrects
n'ont pas de ligne, cette distribution est irrecuperable apres coup, et c'est
elle qui repond au seuil d'auto-validation.

Aucune table de production n'est modifiee hormis is_sensitive : le worker
compare en memoire, un benchmark ne touche pas la donnee qu'il mesure.

comparison_result : id BigInteger et created_at non nullable des la creation,
les rattrapages tardifs etant une reecriture de table et une perte d'historique.
