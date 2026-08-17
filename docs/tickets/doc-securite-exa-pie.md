h2. CONTEXTE

Le guide d'integration exa-pie avait ete redige a partir du source du connecteur,
sans jamais avoir ete confronte a un token reel. Le mock FBI 2.0.6 etant
disponible, il doit devenir la reference d'equipe.

h2. Details

Verifier chaque affirmation du guide contre le comportement observe : claims d'un
token reel, code de get_caller, comportement du middleware dans une requete
complete. Distinguer ce qui est etabli de ce qui reste a verifier.

h2. Criteres d'acceptation

- CA-1 : le claim portant le matricule est etabli par decodage d'un token reel

- CA-2 : toute hypothese infirmee est corrigee et signalee

- CA-3 : le code d'exemple correspond a ce qui est implemente

- CA-4 : la checklist distingue fait / a faire, ordonnee par dependances

- CA-5 : les questions ouvertes decouvertes sont documentees avec leur test

h2. Notes

Trois hypotheses infirmees : le claim n'est pas preferred_username mais sub (plus
prn et user_name, avec desaccord de casse) ; Depends(get_db) dans get_caller est
circulaire ; UserCaller porte le platform_role lu en base, pas les roles du token.

Anomalie confirmee : pie_token et pie_context ne franchissent pas call_next, de
facon silencieuse. A remonter a l'equipe EXA PYTHON.

Question ouverte : pie.yaml declare mode KEYCLOAK, qui lit realm_access.roles,
absent du token FBI. Le filtrage uris-by-roles ne filtre peut-etre rien.

Recette : sans token 400, OPERATOR 1 projet, BUSINESS_ADMIN 2 projets.
