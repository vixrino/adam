# ADAM - Annotation et Données Automatisées


SELECT count(*) total, count(ocr_value) remplis FROM document_field WHERE document_id = 4;   

<img width="1920" height="1080" alt="image" src="https://github.com/user-attachments/assets/48c38830-fbd0-4294-93db-bfeb0969f333" />


Dès qu'un dataset passe en ACTIVE, son schéma est verrouillé, pour ne pas changer le sens des annotations déjà faites. Pour le faire évoluer, on crée une nouvelle version du schéma.
