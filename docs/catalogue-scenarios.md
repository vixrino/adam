# B02 - Catalogue de scénarios

Ce catalogue liste ce que NOTA doit faire dans chaque situation : quand tout se passe bien, quand une erreur survient et dans les cas particuliers. Il sert de référence pour le développement et pour la recette.

## Comment lire les tableaux

| Colonne | Signification |
| --- | --- |
| **Type** | **Normal** : tout se passe bien. **Erreur** : le document ou la demande pose problème. **Panne** : un service ou la base de données ne répond pas. **Sécurité** : une donnée sensible risque d'être exposée. **Cas limite** : situation inhabituelle mais prévue. |
| **Bloque ?** | **Oui** : le traitement s'arrête. **Non** : le traitement continue. |
| **Reprise auto ?** | **Oui** : NOTA réessaie seul. **Non** : une personne doit intervenir. |
| **Code** | Code d'erreur écrit dans le journal, pour retrouver l'incident. |

« Rejeté » veut dire : le document est mis de côté, l'erreur est écrite dans le journal et rien n'est enregistré à moitié.

Les pannes de la base de données et du stockage, communes à tous les services, sont regroupées en partie 6.

---

## 1. Réception des documents

| ID | Type | Situation | Ce que fait NOTA | Bloque ? | Reprise auto ? | Code |
| --- | --- | --- | --- | --- | --- | --- |
| **ING-01** | Normal | Un dossier complet arrive par la MFT | Enregistre le document et lance le préremplissage | Non | Non | - |
| **ING-02** | Normal | Un dossier complet est déposé dans le dossier surveillé | Enregistre le document et lance le préremplissage | Non | Non | - |
| **ING-03** | Erreur | Le fichier ZIP est abîmé ou incomplet | Rejette le dossier et le met en quarantaine | Oui | Non | `ING_ZIP_CORRUPT` |
| **ING-04** | Erreur | Le fichier XML manque ou n'est pas au bon format | Rejette le dossier et le met en quarantaine | Oui | Non | `ING_XML_INVALID` |
| **ING-05** | Panne | La connexion à la MFT est refusée (accès expiré ou invalide) | Arrête la réception et prévient l'administrateur NOTA | Oui | Oui | `ING_AUTH_KO` |
| **ING-06** | Erreur | Le fichier reçu est vide | Rejette le dossier | Oui | Non | `ING_ZIP_EMPTY` |
| **ING-07** | Cas limite | Le même document arrive deux fois | Ignore le second envoi, sans rien retraiter | Non | Non | `ING_DUPLICATE` |
| **ING-08** | Erreur | Le dossier ne contient pas de formulaire CERFA | Rejette le dossier | Oui | Non | `ING_NO_DOC_FOUND` |
| **ING-09** | Erreur | Le PDF est trop volumineux, n'a pas le bon nombre de pages ou n'est pas le bon formulaire | Rejette le document avec un message qui en donne la raison | Oui | Non | `ING_DOC_NON_CONFORME` |

---

## 2. Préparation des images et masquage des données sensibles

| ID | Type | Situation | Ce que fait NOTA | Bloque ? | Reprise auto ? | Code |
| --- | --- | --- | --- | --- | --- | --- |
| **CAV-01** | Normal | Un PDF valide est reçu | Redresse et nettoie les images des pages, puis les enregistre | Non | Non | - |
| **CAV-02** | Normal | Les zones sensibles sont repérées | Masque l'IBAN, le NIR et le numéro MSA sur toutes les pages, puis enregistre le PDF masqué | Non | Non | - |
| **CAV-03** | Sécurité | Les zones sensibles ne sont pas repérées avec assez de certitude | Suspend le document et prévient l'administrateur NOTA | Oui | Non | `CAV_ZONE_SENSIBLES_NOT_FOUND` |
| **CAV-04** | Erreur | L'image est de trop mauvaise qualité | Rejette le document | Oui | Non | `CAV_IMAGE_QUALITY_LOW` |
| **CAV-05** | Erreur | Le masquage échoue sur une partie du document | Rejette le document : rien n'est envoyé à la lecture | Oui | Non | `CAV_PARTIAL_FAIL` |
| **CAV-06** | Erreur | Le formulaire n'est pas reconnu comme un CERFA | Rejette le document ; le réglage de la reconnaissance est à vérifier | Oui | Non | `CAV_CERFA_NOT_RECOGNIZED` |

---

## 3. Lecture par l'IA et préremplissage

| ID | Type | Situation | Ce que fait NOTA | Bloque ? | Reprise auto ? | Code |
| --- | --- | --- | --- | --- | --- | --- |
| **OCR-01** | Normal | L'IA renvoie une lecture complète | Enregistre la lecture, préremplit les champs et met le document à disposition des opérateurs | Non | Non | - |
| **OCR-02** | Panne | Le service de lecture ne répond pas | Réessaie 3 fois ; en cas de nouvel échec, arrête et prévient l'administrateur NOTA | Oui | Oui | `OCR_UNAVAILABLE` |
| **OCR-03** | Erreur | La réponse de l'IA est illisible | Arrête et prévient l'administrateur NOTA | Oui | Non | `OCR_INVALID_RESPONSE` |
| **OCR-04** | Erreur | La réponse est lisible mais ne suit pas le format attendu | Rejette la réponse | Oui | Non | `OCR_SCHEMA_MISMATCH` |
| **OCR-05** | Sécurité | L'accès au service de lecture est refusé | Renouvelle l'accès ; en cas d'échec, prévient l'administrateur NOTA | Oui | Oui | `OCR_AUTH_KO` |
| **OCR-06** | Cas limite | Certains champs manquent dans la réponse | Laisse ces champs vides, les signale comme peu fiables et continue | Non | Non | `OCR_PARTIAL` |
| **OCR-07** | Cas limite | L'IA est peu sûre d'une valeur | Continue ; l'opérateur vérifie la valeur | Non | Non | `OCR_LOW_CONFIDENCE` |
| **OCR-08** | Cas limite | L'IA n'a rien lu sur tout le document | Laisse tous les champs vides : l'opérateur saisit tout à la main | Non | Non | `DS_EMPTY_EXTRACTION` |

---

## 4. Vérification par les opérateurs

| ID | Type | Situation | Ce que fait NOTA | Bloque ? | Reprise auto ? | Code |
| --- | --- | --- | --- | --- | --- | --- |
| **LAB-01** | Normal | Un opérateur soumet sa vérification | Enregistre ses réponses et passe le document au contrôle suivant | Non | Non | - |
| **LAB-02** | Normal | Les réponses concordent | Retient les valeurs finales : le document est validé et prêt à l'export | Non | Non | - |
| **LAB-03** | Normal | L'administrateur métier tranche un champ en revue | Retient sa valeur : le document est validé et prêt à l'export | Non | Non | - |
| **LAB-04** | Erreur | La fenêtre se ferme pendant la saisie | Reprend au dernier champ enregistré, sans perte de saisie | Non | Non | `LAB_SESSION_INTERRUPTED` |
| **LAB-05** | Cas limite | L'IA et les deux opérateurs donnent trois valeurs différentes | Envoie le document en revue et prévient l'administrateur métier | Non | Non | `LAB_REVIEW_REQUIRED` |
| **LAB-07** | Cas limite | Personne ne prend une tâche dans le délai prévu | Prévient l'administrateur métier, qui la réaffecte | Non | Non | `LAB_TASK_UNASSIGNED` |
| **LAB-08** | Erreur | Un export est demandé sur un document pas encore validé | Bloque l'export et prévient l'administrateur métier | Oui | Non | `LAB_EXPORT_INCOMPLETE` |

---

## 5. Tests de la qualité de lecture

| ID | Type | Situation | Ce que fait NOTA | Bloque ? | Reprise auto ? | Code |
| --- | --- | --- | --- | --- | --- | --- |
| **TST-01** | Normal | Un test est lancé sur des documents déjà vérifiés | Fait relire les documents par l'IA, compare avec les réponses des agents, calcule les indicateurs et produit le rapport | Non | Non | - |
| **TST-02** | Erreur | La liste des champs ne correspond pas au lot de documents | Refuse de lancer le test et prévient l'administrateur SMARTDOC | Oui | Non | `TST_SCHEMA_MISMATCH` |
| **TST-03** | Panne | Le service de lecture ne répond pas pendant le test | Réessaie ; en cas de nouvel échec, arrête le test sans donner de résultat partiel | Oui | Oui | `TST_OCR_UNAVAIL` |
| **TST-04** | Erreur | Le test n'a pas de documents vérifiés associés | Refuse de lancer le test et prévient l'administrateur SMARTDOC | Oui | Non | `TST_NO_DATASET` |
| **TST-05** | Cas limite | Un document du test échoue | Réessaie ce document ; en cas de nouvel échec, le note et continue avec les autres | Non | Oui | `TST_DOC_FAIL` |
| **TST-06** | Erreur | Le rapport ne peut pas être produit | Arrête et prévient l'administrateur SMARTDOC | Oui | Non | `TST_REPORT_FAIL` |
| **TST-07** | Cas limite | Le score passe sous le seuil prévu | Produit le rapport avec une alerte de baisse de qualité et prévient l'administrateur SMARTDOC | Non | Non | `TST_MODEL_DRIFT` |
| **TST-08** | Cas limite | On compare deux tests faits dans des conditions différentes | Affiche la comparaison, mais la signale « non comparable » avec la raison | Non | Non | - |
| **TST-09** | Normal | Un administrateur annule un test en cours | Arrête le test proprement, sans résultat partiel | Oui | Non | - |

---

## 6. Base de données et stockage (communs à tous les services)

| ID | Type | Situation | Ce que fait NOTA | Bloque ? | Reprise auto ? | Code |
| --- | --- | --- | --- | --- | --- | --- |
| **INF-01** | Panne | La base de données ne répond pas | Réessaie 3 fois ; en cas de nouvel échec, arrête et prévient l'administrateur NOTA. Une saisie en cours reste conservée | Oui | Oui | `INF_DB_DOWN` |
| **INF-02** | Erreur | Une écriture en base est refusée (doublon, lien manquant) | Annule toute l'opération : rien n'est enregistré à moitié | Oui | Non | `INF_DB_CONSTRAINT` |
| **INF-03** | Cas limite | Une mise à jour de la base est en cours | Met les traitements en pause, puis les reprend seul | Oui | Oui | `INF_DB_MIGRATION` |
| **INF-04** | Panne | Le stockage est plein à 90 % | Suspend la réception de nouveaux documents et prévient l'administrateur NOTA (critique) | Oui | Non | `INF_PVC_FULL` |
| **INF-05** | Cas limite | Le stockage est plein à 80 % | Supprime en avance les fichiers expirés et prévient l'administrateur NOTA (urgent) | Non | Non | `INF_PVC_WARN_80` |
| **INF-06** | Erreur | Un fichier stocké est illisible ou abîmé | Arrête, écrit l'incident dans le journal et lance une vérification | Oui | Non | `INF_FILE_CORRUPTED` |
| **INF-07** | Normal | La durée de conservation RGPD est atteinte | Supprime les données concernées, garde une trace non modifiable et produit un rapport de suppression | Non | Non | - |

---

## Changements par rapport à la version précédente

Les numéros d'origine sont conservés, pour ne pas casser les références déjà faites ailleurs (Jira, tickets).

* **Doublons retirés.** La partie « Création dataset » disparaît : DS-01 est fusionné avec OCR-01, DS-02 est couvert par INF-02, DS-03 et LAB-06 par INF-01, et DS-04 par ING-07. DS-05 devient OCR-08.
* **CAV-07 retiré.** Le formulaire fait 12 pages, et le masquage de toutes les pages est inclus dans CAV-02.
* **Ajouts.** ING-09, pour un document refusé à la réception (déjà en place dans NOTA). TST-08 et TST-09, pour la comparaison de deux tests et l'annulation d'un test (déjà en place).
* **TST-03.** Un test arrêté par une panne ne donne jamais de résultat partiel.

### Détails techniques retirés pour simplifier

Ces précisions restent valables. Elles ne sont simplement plus écrites dans le tableau :

* **OCR-02 :** délais entre les tentatives (10 s, 20 s, 40 s).
* **LAB-01, LAB-02, LAB-03, LAB-05 :** noms des statuts (COMPLETED, VALIDATED, PENDING_REVIEW).
* **OCR-06 et OCR-08 :** nom de l'indicateur `non_fiable=true`.
* **TST-07 :** nom de l'indicateur `DERIVE_DETECTED`.
* **CAV-01 à CAV-06 :** nom de l'outil de détection (DocTR) et traitements d'image (niveaux de gris, rotation, flou gaussien).
* **OCR-01 :** stockage de la réponse en JSONB.
* **OCR-05 :** nom du service d'accès (Azure AD).
* **INF-01 :** mécanisme de coupure automatique (*circuit breaker*).
* **INF-06 :** causes possibles (contrôle d'intégrité CRC, permission refusée).

### Autres changements

* **Titres des parties :** le mot « Tenant » est retiré (« Tenant Ingestion » devient « Réception des documents »).
* **TST-02 :** « au prochain accès » est retiré.
* **Code de ING-09 :** `ING_DOC_NON_CONFORME` est une proposition, il n'existe pas encore dans le code.

