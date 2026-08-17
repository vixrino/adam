h2. CONTEXTE

Les COMPARISON_RESULT sont exploitables un par un mais ne repondent pas a la
question posee : ce moteur OCR est-il bon, et sur quels champs echoue-t-il.

h2. Details

Calculer les agregats d'une execution dans EVALUATION_REPORT et les exposer :
taux d'exactitude global, par type de champ, par section.

h2. Criteres d'acceptation

- CA-1 : le rapport est calcule a la fin d'une execution

- CA-2 : GET rend le rapport d'une execution donnee

- CA-3 : les champs non detectes sont distingues des champs mal lus

- CA-4 : aucune valeur de champ n'apparait dans le rapport ni dans les logs

h2. Notes

Le CA-3 est le plus utile a la decision : un moteur qui ne voit rien et un moteur
qui lit faux n'appellent pas la meme action.

Le CA-4 tient aux donnees traitees, qui portent des IBAN et des NIR.

Depend de T1 et T3.
