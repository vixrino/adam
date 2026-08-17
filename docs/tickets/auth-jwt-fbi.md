h2. CONTEXTE

L'API NOTA n'authentifie personne. get_caller renvoie un UserCaller ecrit en dur
des qu'un JWT est present, ou une erreur 501. Toutes les routes sont donc
ouvertes, et le filtrage multi-tenant n'a jamais pu etre verifie depuis une
requete HTTP reelle.

Le SSO interne est FBI. Le connecteur exa-pie, standard de l'equipe, valide la
signature du token et filtre les URI par role.

h2. Details

Brancher l'API sur FBI via exa-pie et remplacer le caller code en dur par une
identite reelle.

FBI authentifie, la base autorise : le token porte le matricule, la table user
porte l'organisation et le platform_role. Le token ne peut pas porter le
ProjectRole, qui depend du projet.

Verifier de bout en bout contre le mock FBI, avec un OPERATOR et un
BUSINESS_ADMIN.

h2. Criteres d'acceptation

- CA-1 : une requete sans token sur une route non publique est rejetee en 400

- CA-2 : un token valide resout l'appelant en base — matricule, organisation,
  platform_role — et le UserCaller code en dur disparait

- CA-3 : un matricule inconnu de la table user ou un compte inactif rend 403,
  jamais 401 : le token est valide, l'habilitation manque

- CA-4 : le contournement DEV ignore le token, aucune signature n'etant verifiee
  dans ce mode, et resout son matricule en base

- CA-5 : recette contre le mock — un OPERATOR ne voit que ses projets, un
  BUSINESS_ADMIN voit ceux de son organisation

h2. Notes

Le middleware doit etre monte AVANT CORSMiddleware, sinon les preflights OPTIONS
partent en 400 et le front ne peut plus appeler l'API.

pie_token et pie_context ne franchissent pas call_next : les claims sont relus
depuis l'en-tete Authorization. A remonter a l'equipe EXA PYTHON.

Le claim de matricule est sub, avec repli sur prn et user_name.

Reste ouvert : pie.yaml declare mode KEYCLOAK, qui lit realm_access.roles, absent
du token FBI. Le filtrage uris-by-roles ne filtre peut-etre rien.

Guide d'integration : docs/securite-exa-pie.md
