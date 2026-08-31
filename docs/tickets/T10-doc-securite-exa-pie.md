h2. CONTEXTE

Le guide d'integration exa-pie avait ete redige a partir du source du connecteur,
sans avoir ete confronte a un token reel.

h2. Details

Verifier chaque affirmation du guide contre le comportement observe avec le mock
FBI 2.0.6, et corriger ce qui est faux.

h2. Criteres d'acceptation

- CA-1 : le claim portant le matricule est etabli par decodage d'un token reel

- CA-2 : toute hypothese infirmee est corrigee

- CA-3 : le code d'exemple correspond a ce qui est implemente

- CA-4 : la checklist distingue fait / a faire

h2. Notes

Trois hypotheses infirmees : le claim n'est pas preferred_username mais sub ;
Depends(get_db) dans get_caller est circulaire ; UserCaller porte le platform_role
lu en base, pas les roles du token.

Question ouverte : pie.yaml declare mode KEYCLOAK, qui lit realm_access.roles,
absent du token FBI. Le filtrage uris-by-roles ne filtre peut-etre rien.
