# ADAM - Annotation et Données Automatisées

1. Vérifie où est le fichier :   
Test-Path C:\DEV\nota-back\https.truststore.pem   
2. Si False, retrouve-le :    
Get-ChildItem -Recurse -Filter *.pem C:\DEV | Select-Object FullName    
(il est peut-être encore dans le dossier du script de ton manager, pas dans nota-back)    

