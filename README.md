# ADAM - Annotation et Données Automatisées

Dans src/nota_worker/page_image_worker.py, méthode _process_one, juste après l'affectation du nombre de pages :

            file_row.page_count = len(written)
            document.status = DocumentStatus.IN_PROGRESS.value   # <- devient INGESTED

Une seule ligne à changer :

            document.status = DocumentStatus.INGESTED.value
