# ADAM - Annotation et Données Automatisées


Pré-alimentation OCR des champs d'un document `INGESTED` : nouveau worker
`nota_worker/prepopulation/`, endpoints `POST /fields`, `POST /fields/bulk`,
`DELETE /fields/{id}`, migrations `d4e5f6a7b8c9` et `e5f6a7b8c9d0`.

**Prérequis non couvert** : rien ne fait passer un document de `RECEIVED` à
`INGESTED`. `PageImageWorker` pose `IN_PROGRESS` directement, ce qui laisse la
file du worker vide. Une ligne à changer dans `page_image_worker.py` :

```python
document.status = DocumentStatus.INGESTED.value

Impossible ici : ce fichier est sur develop et INGESTED n'existe qu'avec la
migration de cette MR. À faire juste après le merge.
```
