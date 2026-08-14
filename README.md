# ADAM - Annotation et Données Automatisées

Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }               

Vérifie que c'est vide :              
              
Get-NetTCPConnection -LocalPort 8000 -State Listen              
                     
Aucune sortie = le port est libre.                     
              
Puis relance :
                            
uv run uvicorn nota_api.main:app --port 8000
