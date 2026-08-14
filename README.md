# ADAM - Annotation et Données Automatisées

@"
fr.bdf.fbi.mock.oauth2.client=FBI-Appli-Demo
fr.bdf.fbi.mock.oauth2.resourceId=framedev-api
fr.bdf.fbi.mock.oauth2.scope=SCOPE
fr.bdf.fbi.mock.oauth2.redirectURIs=http://localhost:4200/
server.port=9000
"@ | Out-File -Encoding ascii C:\DEV\fbi-mock\application.properties

@"
zuul.routes.fbi.url=http://localhost:9000
"@ | Out-File -Encoding ascii C:\DEV\fbi-mock\application-oauth2.properties
