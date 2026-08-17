# Backlog

Libelles Jira, au format de l'equipe. A copier tels quels dans le ticket.

| # | Sujet | Depend de |
|---|-------|-----------|
| T1 | Modele de donnees des recettes de test | — |
| T2 | API des recettes de test | T1 |
| T3 | Worker d'execution des recettes | T1 |
| T4 | Rapport d'evaluation | T1, T3 |
| T5 | Connecteur OCR Mistral | — |
| T6 | Verrou concurrent sur PrepopulationWorker | — |
| T7 | Champs repetables de bout en bout | — |
| T8 | Fermer les routes par des dependances | raccordement FBI |
| T9 | Deduire agent_id de l'appelant | raccordement FBI |

T5, T6 et T7 sont independants et peuvent partir en parallele.

T8 doit preceder la suppression de API_DISABLE_JWT_VALIDATION.
