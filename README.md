### Parcours d'annotation et réception des formulaires

**Ce qui a été fait**
L'application sait maintenant recevoir un formulaire et le préparer pour les opérateurs.
Quand un PDF est déposé, le système vérifie que c'est bien un PDF valide, refuse les fichiers abîmés ou d'un autre type, et ne garde jamais deux fois le même fichier. Chaque page est ensuite transformée en image de bonne qualité, pour que l'opérateur puisse la lire confortablement à l'écran.

Autres points livrés :

* Le parcours complet d'un opérateur sur un document : prendre une tâche, saisir ou corriger les valeurs, soumettre.
* La gestion des listes de champs à remplir (créer, modifier, dupliquer, verrouiller une liste déjà utilisée pour ne pas casser les documents existants).
* La lecture des dates et des nombres écrits « à la française » (par exemple 12/03/2026 ou 1 250,50).
* De nouveaux accès pour l'interface : afficher le PDF d'origine, l'image d'une page et l'avancement d'un document.
* Environ 135 tests automatiques pour fiabiliser ces fonctions.

**Pourquoi c'est important**
Avant, l'application stockait des données mais ne recevait pas encore de vrais documents. C'est ce qui permet à l'opérateur de travailler sur un formulaire réel, page par page.

---

### Sécurité, droits d'accès et premiers traitements automatiques

**Ce qui a été fait**
L'application est maintenant raccordée à l'authentification de la Banque de France : un agent se connecte avec son compte habituel, et l'application reconnaît son matricule.
Chaque utilisateur ne voit plus que les données de son organisation et des projets auxquels il est affecté. Les rôles dans un projet (opérateur, administrateur métier…) sont séparés des rôles sur la plateforme (administrateur technique).

Autres points livrés :

* Un traitement automatique qui suit en continu l'avancement de chaque document et le fait passer à l'étape suivante.
* Un traitement automatique d'un document dès son arrivée, pour que l'opérateur n'ait plus qu'à vérifier.
* Le premier raccordement à l'intelligence artificielle (Mistral), qui lit chaque page et propose une valeur pour chaque champ.
* Un guide de sécurité qui explique comment l'authentification est branchée et ce qu'il reste à faire.

**Pourquoi c'est important**
Sans cette étape, l'application ne pouvait pas être ouverte à de vrais agents : il fallait d'abord savoir qui se connecte et ce que chacun voit. Le préremplissage par l'IA est aussi le premier pas vers le vrai gain de temps attendu : vérifier au lieu de ressaisir.

---

### Le formulaire de surendettement complet

**Ce qui a été fait**
La liste complète des champs du formulaire officiel de surendettement (12 pages) a été décrite dans l'application.
La lecture par l'IA a été améliorée :

* l'IA reconnaît d'abord de quelle page il s'agit, même si les pages ont été scannées dans le désordre, puis remet le document dans le bon ordre ;
* elle ne confond plus le texte imprimé du formulaire avec les réponses de la personne ;
* elle n'est plus programmée pour un seul formulaire : elle suit la liste des champs du lot de documents, ce qui permettra de l'utiliser pour d'autres types de documents.

Autres points livrés :

* Un document incomplet ou qui n'est pas le bon formulaire est mis de côté avec un message d'erreur clair.
* Un lot de documents suit un cycle de vie : brouillon, actif, archivé.
* Un administrateur peut affecter une personne de l'annuaire à un projet avant même sa première connexion.
* L'application et tous ses traitements automatiques se lancent en une seule commande.

**Pourquoi c'est important**
C'est cette étape qui adapte l'outil au vrai besoin métier : le formulaire de surendettement tel que les agents le reçoivent, avec des pages parfois mélangées ou mal remplies.

---

### Tableaux du formulaire et outil de mesure de la qualité

**Ce qui a été fait**
L'IA lit maintenant chaque ligne des tableaux du formulaire (liste des crédits, des dettes, des personnes à charge), et plus seulement des champs isolés. Les prêts à la consommation n° 7 et 8 de la page 11 ont été ajoutés.
Un outil de test a été construit : il fait relire par l'IA des documents déjà vérifiés par des agents, puis compare les deux réponses champ par champ. Il en tire des indicateurs simples, comme la part des valeurs bien lues et la part des valeurs trouvées.

**Pourquoi c'est important**
Jusqu'ici, on ne pouvait juger la lecture que sur quelques exemples. Cet outil donne une mesure chiffrée et répétable de la qualité de la lecture : c'est ce qui permettra de décider si l'IA est prête pour la production, et de comparer deux moteurs entre eux.

---

### Page des métriques et tests fiables

**Ce qui a été fait**
Côté backend, la page des métriques est prête : les résultats d'un test peuvent être filtrés par page, par rubrique ou par type de champ, consultés champ par champ et exportés en rapport PDF.
L'outil de test a été rendu plus fiable :

* un test se fait toujours sur une copie figée des documents vérifiés, pour que deux tests soient vraiment comparables ;
* l'outil refuse de comparer deux tests qui n'ont pas été faits dans les mêmes conditions ;
* seul un administrateur peut modifier les consignes données à l'IA ;
* on peut suivre l'avancement d'un test en cours de route.

**Pourquoi c'est important**
Un chiffre n'a de valeur que si on peut lui faire confiance. Ces garanties évitent de conclure à une amélioration de l'IA à partir de tests qui ne seraient pas comparables.

---

### Premiers tests sur de vrais formulaires

**Ce qui a été fait**
L'outil de test a été lancé sur dix formulaires réels vérifiés à la main.

* **Premier test, sur un formulaire :** 97 valeurs sur 101 bien lues. 2 des 4 erreurs venaient de la liste des champs. Elles ont été corrigées.
* **La vérification des dix formulaires** a fait apparaître d'autres défauts de la liste des champs, qui ont été corrigés : par exemple, l'ordre des rubriques est aligné sur le formulaire papier. Les documents déjà vérifiés ont été convertis sans perdre le travail des agents.
* **Un score qui baissait sans que la lecture ait empiré :** le score est passé de 95,3 % à 87,9 %, parce que l'outil comptait comme des fautes de simples différences de présentation (une virgule, par exemple). Il compare désormais les lettres et les chiffres sans tenir compte de la ponctuation. Deux erreurs de calcul ont aussi été corrigées.
* **Résultat sur les dix formulaires : 95,7 %** de valeurs bien lues et trouvées.
* **Un second test identique** a donné 94,7 % : l'IA ne répond pas exactement pareil à chaque passage, un écart d'environ 1 point ne prouve donc rien.
* **Des consignes enrichies** demandaient à l'IA de corriger ses fautes (par exemple « PRANCE » → « FRANCE »). Le résultat était moins bon (93,7 %) : l'IA « corrigeait » des valeurs justes. Elles n'ont pas été retenues.

**Pourquoi c'est important**
C'est la première mesure de la qualité de l'IA sur de vrais formulaires. Elle montre aussi qu'il faut comprendre une erreur avant d'en accuser l'IA : plusieurs baisses venaient de la liste des champs ou de la façon de compter, pas de la lecture.

---

### Charger le dataset de l'étude

Pour charger les formulaires de l'étude déjà remplis et validés, il faut la planilha (`.xlsx`) et le dossier des PDF. Le `.xlsx` se lit sans openpyxl, et chaque `load` crée un nouveau dataset.

```powershell
uv run python scripts\seed_study.py convert etude.xlsx -o study.json
uv run python scripts\seed_study.py load study.json --pdf-dir .\pdfs --project-id <id du projet dgser> --dry-run
uv run python scripts\seed_study.py load study.json --pdf-dir .\pdfs --project-id <id du projet dgser>
```
