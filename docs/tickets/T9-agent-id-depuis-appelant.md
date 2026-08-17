h2. CONTEXTE

JobIn recoit agent_id dans le corps de la requete. Un appelant peut donc attribuer
une annotation a un autre operateur, et le consensus s'appuie sur une donnee
declarative.

h2. Details

Retirer agent_id de JobIn et le deduire du UserCaller.

h2. Criteres d'acceptation

- CA-1 : agent_id ne figure plus dans le schema d'entree

- CA-2 : le job cree porte l'id de l'utilisateur authentifie

- CA-3 : le comptage du consensus deduplique par agent_id

h2. Notes

Le CA-3 est un defaut distinct, releve au passage : submitted_count ne deduplique
pas, un meme operateur qui soumet plusieurs jobs satisfait donc
required_operators a lui seul. A confirmer avec la logique metier avant
modification.

Depend du raccordement FBI.
