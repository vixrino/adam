# Backlog

Libelles Jira, au format de l'equipe. A copier tels quels dans le ticket.

| # | Sujet | Depend de |
|---|-------|-----------|
| T1 | Modele de donnees des recettes de test | — |
| T5 | Connecteur OCR Mistral | — |
| T6 | Verrou concurrent sur PrepopulationWorker | — |
| T7 | Champs repetables de bout en bout | — |
| T8 | Fermer les routes par des dependances | raccordement FBI |
| T9 | Deduire agent_id de l'appelant | raccordement FBI |
| T10 | Verification du guide exa-pie | fait |

T1, T5, T6 et T7 sont independants et peuvent partir en parallele.

T8 doit preceder la suppression de API_DISABLE_JWT_VALIDATION.

Ce que T1 rendra possible — endpoints des recettes, worker d'execution, agregats
du rapport — sera decoupe une fois les tables posees, quand le besoin sera cadre.
