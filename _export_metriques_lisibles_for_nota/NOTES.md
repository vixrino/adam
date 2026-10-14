# Report vers nota : metriques lisibles et reponse allegee

`changements.patch` = `feature/metriques-lisibles` par dessus
`feature/metriques-benchmark`, `adam_*` renomme en `nota_*`. Pas de migration :
les colonnes vp/fp/fn/vn de evaluation_report ne changent pas.

    git apply --check changements.patch
    git apply changements.patch
    uv run --all-extras pytest

Puis redemarrer l'API.

## Pour l'IHM (cles renommees)

| Avant | Apres |
|---|---|
| vp / fp / fn / vn | justes / fausses / manquees / inventees / vides (cases disjointes) |
| f1 | score |
| precision / rappel | taux_lectures_justes / taux_valeurs_trouvees |
| ic95_* | fourchette_* (global et groupes seulement) |
| effectif_suffisant | assez_de_donnees |
| field_key, value_type, sensitive (par_champ) | champ, type, sensible |
| config.seuil_f1 | config.score_minimal (l'ancien nom reste lu) |
| echantillon.couverture / champs_juges / faible | part_verifiee / champs_verifies / trop_petit |
| comparaison : delta, f1_a, delta_f1 | evolution, score_a, evolution |

`par_champ` ne liste plus que les champs en erreur (`champs_sans_erreur` les
compte) ; `?tous_les_champs=true` rend la liste complete. La comparaison ne
liste que les champs dont le score a bouge (`champs_inchanges`).

## Si `git apply` refuse

Copier les 4 fichiers de `fichiers_complets/` (deja en nota_*) par dessus ceux
de nota, puis a la main :
- `src/nota_api/main.py` : sous l'import CORS,
  `from fastapi.middleware.gzip import GZipMiddleware` ; apres le bloc
  `app.add_middleware(CORSMiddleware, ...)`,
  `app.add_middleware(GZipMiddleware, minimum_size=1000)`.
- `src/nota_core/models/test_recipe.py` : commentaire seulement
  (`seuil_f1` -> `score_minimal`), facultatif.
