# Roadmap : page des métriques et export PDF

Échéance : **24 novembre 2026**. Équipe : Lucas (back), Daniel (front).
Maquette retenue : écran « Rapport » et « PDF généré par les filtres ».

État au 9 novembre : **back terminé**, dans adam (PR #12 à #15) et dans nota.

| # | Tâche | Qui | Jours | État |
|---|---|---|---|---|
| 1 | Filtres et chiffres par champ dans l'API | Lucas | 2 | Fait |
| 2 | PDF filtré, à l'identique de la maquette | Lucas | 3,5 | Fait |
| 3 | Report dans nota | Lucas | 1 | Fait |
| 4 | Haut de la page et sections | Daniel | 2 | À faire |
| 5 | Tableau des champs en erreur, avec filtres | Daniel | 2 | À faire |
| 6 | Panneau du champ sélectionné | Daniel | 1,5 | À faire |
| 7 | Comparaison avec une exécution précédente | Daniel | 1 | À faire |
| 8 | Bouton PDF, cas particuliers, tests | Daniel | 2 | À faire |
| 9 | Test commun sur nota | Lucas + Daniel | 2 | À faire |

Il reste à Daniel 10,5 jours de travail pour 10 jours ouvrés (le 11 est
férié). Si la date glisse, la tâche 7 passe en version 2.

## Décisions

- **Découpe de la page autour du champ : abandonnée.** Le moteur OCR ne rend
  pas la position des champs. Les extraits montrent le document, la page, la
  valeur attendue et la valeur lue.
- **Grand pourcentage : `global.taux_lectures_justes`**, page et PDF. Les
  chiffres n'ont pas à reprendre ceux de la maquette.
- **Comparaison : deux exécutions de la même recette.** Mêmes documents, même
  vérité ; seul le moteur change (`ocr_provider`, `ocr_model_id`). C'est ce
  qui dit si une nouvelle version de l'OCR fait mieux.
- **Champs sensibles :** seuls noms, prénoms, dates et lieux de naissance et
  IBAN sont masqués. Téléphone, courriel, adresse : pas pour l'instant.
- **Polices :** nota n'a pas les fichiers de `services/polices` ; le PDF y
  prend Helvetica et Courier, intégrés à PyMuPDF.

## Où le front trouve chaque donnée

| Élément de la page | API |
|---|---|
| Taux, marge, « N lus correctement sur M » | `/metriques` → `global.taux_lectures_justes`, `fourchette_lectures_justes`, `justes` |
| Répartition des valeurs | `global.justes`, `fausses`, `manquees`, `inventees`, `vides` |
| En-tête « Dataset X · recette #N » | `/metriques` → `dataset`, `recette` |
| Tableau par section | `par_section`, libellé dans `par_section[].libelle` |
| Champs en erreur | `par_champ[]` : `champ`, `section_libelle`, `type`, `reussite`, `documents_en_erreur`, `echec_principal` |
| Filtres et « N champs correspondent » | paramètres `recherche`, `type_champ`, `reussite_inferieure_a`, `type_erreur`, `section` ; réponse `selection` |
| Documents en erreur d'un champ, « Document i sur N » | `/ecarts?champ=<par_champ[].champ>` ; N dans l'en-tête `X-Total-Count` |
| Comparaison par champ et par section | `/test-executions/comparaison?a=<référence>&b=<analysée>` → `par_champ[]` (`reussite_a`, `reussite_b`, `ecart_pts`), `par_section`, `comparable`, `raisons` |
| Bouton PDF | `/test-executions/{id}/metriques.pdf`, mêmes filtres que la page |

## Générer un PDF sans IHM

```bash
python scripts/demo_metriques.py                 # base de démo, une exécution
POSTGRES_DB=<base>_demo_metriques python scripts/exporter_rapport_pdf.py      # liste
POSTGRES_DB=<base>_demo_metriques python scripts/exporter_rapport_pdf.py <id> # PDF
```

## Reste à vérifier

- Un passage sur de vraies données : vrai CERFA, Mistral, vérité saisie par
  un humain, puis page et PDF. Seules les données de démo ont servi.
- Deux exécutions d'une même recette, pour développer et tester la
  comparaison : la démo n'en crée qu'une.
- Le téléchargement du PDF par l'API réelle, une fois FBI débloqué.
