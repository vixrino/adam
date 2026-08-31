h2. CONTEXTE

OcrProvider declare PULSAR et MISTRAL, aucun des deux n'est ecrit. Le seul
connecteur existant est MockOcrConnector, qui rend des valeurs synthetiques.
Toute la chaine de pre-alimentation tourne donc a vide.

h2. Details

Ecrire un connecteur implementant BaseOcrConnector.extract, qui soumet les images
de page a l'API Mistral et rend un SmartdocDocument conforme au contrat v0.3.

h2. Criteres d'acceptation

- CA-1 : extract rend un SmartdocDocument valide a partir d'images reelles

- CA-2 : les KVPair portent des id pointes correspondant aux field_key du schema,
  sans quoi le merger n'en rapproche aucun

- CA-3 : un moteur injoignable leve OcrConnectorError ; un moteur qui ne detecte
  rien rend None

- CA-4 : le connecteur se substitue au mock sans modifier une ligne du worker

- CA-5 : la cle d'API vient de la configuration, jamais du code

h2. Notes

Le CA-2 est le coeur du travail. Un OCR generique rend du texte positionne, pas
des identifiants de schema : il faut soit envoyer le schema attendu au modele,
soit rapprocher les polygones apres coup. Sans cela le connecteur produit un
document que le merger ignore integralement, et le document se retrouve avec ses
champs vides sans qu'aucune erreur ne le signale.

Trancher en amont : endpoint OCR dedie ou modele multimodal prompte. Les deux ne
rendent pas la meme chose et ne demandent pas le meme travail.
