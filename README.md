# ADAM - Annotation et Données Automatisées

[https://vibeslops.luckeysystems.com/](https://t.co/8r990RLwpe)

┌──────────────────────┬─────────────────────────────────────────────────────────────────┬────────────────────────────────┐
│        Étape         │                         Ce qui se passe                         │          Métriques ?           │
├──────────────────────┼─────────────────────────────────────────────────────────────────┼────────────────────────────────┤
│ 1. Dépôt dans le     │ PDF ingéré, pages rendues en images                             │ non                            │
│ dataset              │                                                                 │                                │
├──────────────────────┼─────────────────────────────────────────────────────────────────┼────────────────────────────────┤
│ 2. Pré-alimentation  │ Mistral lit le document et préremplit les champs (ocr_value)    │ non : il n'y a encore aucune   │
│                      │                                                                 │ vérité à laquelle comparer     │
├──────────────────────┼─────────────────────────────────────────────────────────────────┼────────────────────────────────┤
│ 3. Labellisation     │ l'opérateur corrige ou valide les champs : ça crée des          │ non                            │
│ métier               │ field_proposal, et resolved_value devient la vérité             │                                │
├──────────────────────┼─────────────────────────────────────────────────────────────────┼────────────────────────────────┤
│ 4. Lancement d'un    │ quelqu'un crée une recette (les documents labellisés) et lance  │ —                              │
│ test                 │ une exécution (POST /test-executions)                           │                                │
├──────────────────────┼─────────────────────────────────────────────────────────────────┼────────────────────────────────┤
│ 5. Exécution par le  │ Mistral relit les documents de la recette, et la lecture est    │ les comptes sont enregistrés   │
│ worker               │ comparée à la vérité de l'étape 3                               │                                │
├──────────────────────┼─────────────────────────────────────────────────────────────────┼────────────────────────────────┤
│ 6. Consultation      │ GET /test-executions/{id}/metriques                             │ les métriques sont calculées   │
│                      │                                                                 │ ici                            │
└──────────────────────┴─────────────────────────────────────────────────────────────────┴────────────────────────────────┘
