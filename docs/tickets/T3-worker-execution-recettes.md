h2. CONTEXTE

Une TEST_EXECUTION en attente doit etre traitee hors du cycle HTTP : une recette
porte potentiellement des centaines de documents.

h2. Details

Worker sur le modele de BaseWorker. Il prend les executions en attente, rejoue la
recette, ecrit un COMPARISON_RESULT par champ compare, puis marque l'execution.

h2. Criteres d'acceptation

- CA-1 : une execution en attente est traitee, une execution terminee est ignoree

- CA-2 : deux instances du worker ne traitent jamais la meme execution

- CA-3 : un echec sur une execution ne bloque pas les suivantes

- CA-4 : point d'entree dedie, sur le modele de progress_main

h2. Notes

Le verrou du CA-2 est obligatoire ici, contrairement au worker d'observation :
deux pods qui rejouent la meme campagne, c'est deux fois la facture du moteur OCR.
Reprendre le FOR UPDATE SKIP LOCKED de PageImageWorker.

Depend de T1.
