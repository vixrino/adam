# ADAM - Annotation et Données Automatisées


Invoke-RestMethod "http://localhost:8001/api/v1/projects" -Headers @{Authorization="Bearer $op"}

Puis, sur une ligne séparée :

Invoke-RestMethod "http://localhost:8001/api/v1/projects" -Headers @{Authorization="Bearer $ba"}
