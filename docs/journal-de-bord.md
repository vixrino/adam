# 0 - Journal de bord

## Journal de bord, NOTA

> Journal de bord du projet. Objectif : garder une trace de ce qui a été livré et pourquoi, sans entrer dans le détail du code.

---

### Juin 2026, Fondations techniques

**Ce qui a été fait**
Mise en place de toute la base technique du projet (backend) : structure du dépôt, configuration de l'application, et le modèle de données complet (toutes les tables qui décrivent ce qu'est un projet, un dataset, un document, un champ, etc.).
Côté API, les premières routes ont été créées pour permettre de créer, lire, modifier et supprimer les principales entités, avec un système d'authentification posé dès le départ.
Une interface de documentation technique (Swagger) a aussi été mise en place pour pouvoir consulter et tester l'API facilement.

**Pourquoi c'est important**
Cette étape ne contient pas encore de logique métier de labellisation : c'est la fondation sur laquelle tout le reste va se construire. Sans cette base (modèle de données, configuration, structure du projet), rien de la suite n'aurait pu démarrer.
On a choisi un seul service API avec des droits d'accès gérés au cas par cas, plutôt que deux services séparés (un public via FBL, un interne via Key de service). Plus simple à maintenir et à déployer, sans perte de sécurité.

---

### Juin 2026, Logique de labellisation et consensus

**Ce qui a été fait**
C'est cette étape qui a donné vie au cœur métier de NOTA : le consensus.
Pour rappel, le principe : un document est d'abord traité par un opérateur (étape de validation), puis vérifié par un second opérateur (étape de consensus). Le système compare maintenant automatiquement les réponses des deux opérateurs. Si une majorité se dégage sur la valeur d'un champ, le champ est considéré comme validé. Si les avis divergent trop, le document est mis en attente pour qu'un administrateur tranche.
Cette vérification se fait automatiquement, juste après qu'un opérateur ait soumis son travail, sans que personne n'ait besoin de la déclencher manuellement.

Autres points livrés :

* Le système journalise maintenant ses actions de façon standardisée, ce qui facilitera le diagnostic en cas de problème en production.
* Quand l'OCR ne détecte pas un champ sur un document, ce champ apparaît maintenant tout de même dans l'interface (avec une valeur vide) plutôt que de disparaître complètement. C'est important pour que l'opérateur sache qu'il doit le renseigner à la main.
* Une bonne partie du travail a aussi été consacrée à écrire des tests pour fiabiliser tout ça (environ 80 % du code est aujourd'hui testé).
* Une série de petites corrections a suivi une revue de code par un collègue, principalement pour fiabiliser la façon dont l'application gère ses connexions à la base de données en arrière-plan.

**Pourquoi c'est important**
Avant cette étape, l'application savait stocker des données mais ne savait pas encore "décider" automatiquement quand un champ était correctement labellisé. C'est ce mécanisme de consensus qui rend l'outil réellement utile pour le métier : sans lui, il faudrait qu'un humain compare manuellement chaque réponse.
À noter pour la suite : à ce stade, la vérification de consensus ne se déclenche qu'au moment où l'opérateur soumet son travail. La suite prévoit de rendre ce mécanisme plus robuste, avec une vérification qui tourne en continu plutôt qu'à un seul moment précis.

---

### Fin juin – juillet 2026, Parcours d'annotation et réception des formulaires

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

### Fin juillet – août 2026, Sécurité, droits d'accès et premiers traitements automatiques

**Ce qui a été fait**
L'application est maintenant raccordée à l'authentification de la Banque de France : un agent se connecte avec son compte habituel, et l'application reconnaît son matricule.
Chaque utilisateur ne voit plus que les données de son organisation et des projets auxquels il est affecté. Les rôles sur un projet (opérateur, administrateur métier…) sont séparés des rôles sur la plateforme (administrateur technique).

Autres points livrés :

* Un traitement automatique qui suit en continu l'avancement de chaque document et le fait passer à l'étape suivante. C'est la vérification « en continu » annoncée plus haut.
* Un traitement automatique qui préremplit les champs d'un document dès son arrivée, pour que l'opérateur n'ait plus qu'à vérifier.
* Le premier raccordement à un moteur de lecture par intelligence artificielle (Mistral), qui lit chaque page et propose une valeur pour chaque champ.
* Le modèle de données des futurs tests de qualité de la lecture.
* Un guide de sécurité qui explique comment l'authentification est branchée et ce qu'il reste à faire.

**Pourquoi c'est important**
Sans cette étape, l'application ne pouvait pas être ouverte à de vrais agents : il fallait d'abord savoir qui se connecte et limiter ce que chacun voit. Le préremplissage par l'IA est aussi le premier pas vers le vrai gain de temps attendu : vérifier au lieu de ressaisir.

---

### Septembre – mi-octobre 2026, Le formulaire de surendettement complet

**Ce qui a été fait**
La liste complète des champs du formulaire officiel de surendettement (12 pages) a été décrite dans l'application, puis corrigée en la comparant à des formulaires réels.
La lecture par l'IA a été nettement améliorée :

* l'IA reconnaît d'abord de quelle page du formulaire il s'agit, même si les pages ont été scannées dans le désordre, puis remet le document dans le bon ordre ;
* elle ne confond plus le texte imprimé du formulaire avec les réponses de la personne ;
* elle distingue une case vide d'une case non cochée ;
* elle n'est plus programmée pour un seul formulaire : elle suit la liste des champs du lot de documents, ce qui permettra d'accueillir d'autres types de documents.

Autres points livrés :

* Un document trop volumineux, incomplet ou qui n'est pas le bon formulaire est mis de côté avec un message d'erreur clair.
* Un lot de documents suit maintenant un cycle de vie : brouillon, actif, archivé.
* Un administrateur peut affecter une personne de l'annuaire à un projet avant même sa première connexion.
* L'application et tous ses traitements automatiques se lancent en une seule commande.

**Pourquoi c'est important**
C'est cette étape qui adapte l'outil au vrai besoin métier : le formulaire de surendettement tel que les agents le reçoivent, avec des pages parfois mélangées ou mal remplies.

---

### Mi-octobre – début novembre 2026, Tableaux du formulaire et outil de mesure de la qualité

**Ce qui a été fait**
L'IA lit maintenant chaque ligne des tableaux du formulaire (liste des crédits, des dettes, des personnes à charge…), et plus seulement les champs isolés. Les prêts à la consommation n° 7 et 8 de la page 11 ont été ajoutés.
Un outil de test a été construit : il fait relire par l'IA des documents déjà vérifiés par des agents, puis compare les deux réponses champ par champ. Il en tire des indicateurs simples, comme la part des valeurs bien lues et la part des valeurs trouvées.

**Pourquoi c'est important**
Jusqu'ici, on ne pouvait juger l'IA qu'« à l'œil » sur quelques exemples. Cet outil donne une mesure chiffrée et répétable de la qualité de la lecture : c'est ce qui permettra de décider, preuves à l'appui, si l'IA est prête pour la production et de comparer deux moteurs entre eux.

---

### Novembre 2026, Page des métriques et tests fiables

**Ce qui a été fait**
Côté backend, la page des métriques est prête : les résultats d'un test peuvent être filtrés par page, par rubrique ou par type de champ, consultés champ par champ et exportés en rapport PDF, à l'identique de la maquette retenue.
L'outil de test a été rendu plus fiable :

* un test se fait toujours sur une copie figée des documents vérifiés, pour que deux tests soient vraiment comparables ;
* l'outil refuse de comparer deux tests qui n'ont pas été faits dans les mêmes conditions ;
* seul un administrateur peut modifier les consignes données à l'IA ;
* on peut suivre l'avancement d'un test et l'annuler en cours de route.

Une relecture complète a permis de corriger cinq défauts avant la mise en service.

**Pourquoi c'est important**
Un chiffre n'a de valeur que si on peut lui faire confiance. Ces garanties évitent de conclure à une amélioration ou à une dégradation de l'IA à partir de tests qui ne seraient pas comparables.

---

### 16 – 19 novembre 2026, Premiers tests sur de vrais formulaires

**Ce qui a été fait**
L'outil de test a été lancé, en une seule commande, sur dix formulaires réels vérifiés à la main.

* **Premier test, sur un formulaire :** 97 valeurs sur 101 bien lues. 2 des 4 erreurs venaient de la liste des champs, pas de l'IA. Elles ont été corrigées.
* **La vérification des dix formulaires** a fait apparaître d'autres défauts de la liste des champs. Ils ont été corrigés : une date « depuis le » par situation professionnelle, l'ordre des rubriques aligné sur le formulaire papier, une mention imprimée qui n'est plus prise pour une réponse. Les documents déjà vérifiés ont été convertis sans perdre le travail des agents.
* **Un score qui baissait sans que la lecture ait empiré :** le score est passé de 95,3 % à 87,9 %, parce que l'outil comptait comme des fautes de simples différences de présentation (une virgule, un espace). L'outil compare désormais les lettres et les chiffres sans tenir compte de la ponctuation. Deux erreurs de calcul ont aussi été corrigées.
* **Résultat sur les dix formulaires : 95,7 %** de valeurs bien lues et trouvées.
* **Un second test identique a donné 94,7 %.** L'IA ne répond pas exactement pareil à chaque passage : un écart d'environ 1 point ne prouve donc rien.
* **Des consignes enrichies ont été essayées** pour aider l'IA à corriger ses fautes (par exemple « PRANCE » → « FRANCE »). Résultat moins bon (93,7 %) : l'IA « corrigeait » des valeurs justes. Elles ne sont pas retenues.

**Pourquoi c'est important**
C'est la première mesure de la qualité de l'IA sur de vrais formulaires. Elle montre aussi qu'il faut comprendre chaque écart avant d'en accuser l'IA : plusieurs baisses venaient de la liste des champs ou de la façon de compter, pas de la lecture.

---

### À venir

* Faire vérifier ces dix formulaires, puis de nouveaux, par trois opérateurs, pour obtenir une référence fiable.
* Mettre en service la page des métriques avec le frontend.
* Raccorder un second moteur de lecture pour comparer les fournisseurs.
* Préparer les tests de charge.
* Transmettre à l'équipe la documentation pour faire vivre l'outil de test.
