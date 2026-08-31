h2. CONTEXTE

PageImageWorker prend ses documents avec FOR UPDATE SKIP LOCKED.
PrepopulationWorker fait un SELECT nu.

h2. Details

Aligner la selection des candidats sur celle de PageImageWorker.

h2. Criteres d'acceptation

- CA-1 : deux instances du worker ne traitent jamais le meme document

- CA-2 : le lot d'une instance n'attend pas la liberation du lot de l'autre

h2. Notes

L'idempotence evite aujourd'hui les doublons en base, mais l'appel OCR est paye
deux fois — et il sera probablement facture a l'appel.
