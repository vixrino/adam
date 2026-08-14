# ADAM - Annotation et Données Automatisées

mkdir "$env:USERPROFILE\FBI_USER_REPOSITORY"

@"
{
  "uid": "i659418",
  "secret": "motdepasse",
  "principal": "I659418",
  "lastName": "Operateur",
  "firstName": "Test",
  "email": "test.operateur@banque-france.fr",
  "phone": "0101010101",
  "roles": "OPERATOR",
  "scope": "SCOPE",
  "CodeUA": "TestUA"
}
"@ | Out-File -Encoding ascii "$env:USERPROFILE\FBI_USER_REPOSITORY\i659418.json"

@"
{
  "uid": "v654846",
  "secret": "motdepasse",
  "principal": "V654846",
  "lastName": "AdminMetier",
  "firstName": "Test",
  "email": "test.admin@banque-france.fr",
  "phone": "0101010101",
  "roles": "ADMIN",
  "scope": "SCOPE",
  "CodeUA": "TestUA"
}
"@ | Out-File -Encoding ascii "$env:USERPROFILE\FBI_USER_REPOSITORY\v654846.json"

