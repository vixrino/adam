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

### Fin juin – juillet 2026 : recevoir les formulaires

**Ce qui a été fait**

* L'application reçoit les formulaires en PDF. Elle refuse les fichiers abîmés et ne garde jamais deux fois le même.
* Chaque page est transformée en image, pour que l'opérateur la lise à l'écran.
* L'opérateur peut prendre un document, saisir ou corriger les valeurs, puis soumettre son travail.
* Les dates et les nombres écrits « à la française » sont bien compris (12/03/2026, 1 250,50).

**Pourquoi c'est important**
L'opérateur peut maintenant travailler sur un vrai formulaire, page par page.

---

### Août 2026 : sécurité et préremplissage par l'IA

**Ce qui a été fait**

* Les agents se connectent avec leur compte Banque de France habituel.
* Chacun ne voit que les projets auxquels il est affecté.
* L'application suit seule l'avancement de chaque document et le fait passer à l'étape suivante.
* Une IA (Mistral) lit chaque page et préremplit les champs. L'opérateur n'a plus qu'à vérifier.

**Pourquoi c'est important**
L'application peut être ouverte à de vrais agents, et l'IA fait gagner du temps : on vérifie au lieu de ressaisir.

---

### Septembre – octobre 2026 : le formulaire de surendettement complet

**Ce qui a été fait**

* Les 12 pages du formulaire officiel sont décrites dans l'application.
* L'IA reconnaît chaque page, même scannée dans le désordre, et remet le document dans l'ordre.
* L'IA ne confond plus le texte imprimé du formulaire avec les réponses de la personne.
* L'IA lit chaque ligne des tableaux (crédits, dettes, personnes à charge).
* Un document incomplet ou qui n'est pas le bon formulaire est mis de côté avec un message clair.

**Pourquoi c'est important**
L'outil est adapté aux formulaires tels que les agents les reçoivent vraiment.

---

### Octobre – novembre 2026 : mesurer la qualité de l'IA

**Ce qui a été fait**

* Un outil de test fait relire par l'IA des documents déjà vérifiés par des agents, et compare les deux réponses champ par champ.
* Il calcule la part des valeurs bien lues et la part des valeurs trouvées.
* Les résultats s'affichent sur une page de métriques, avec des filtres, et s'exportent en PDF.
* Deux tests ne sont comparés que s'ils ont été faits dans les mêmes conditions.

**Pourquoi c'est important**
On ne juge plus l'IA « à l'œil » : on a un chiffre fiable pour décider si elle est prête pour la production.

---

### 16 – 19 novembre 2026 : premiers tests sur de vrais formulaires

**Ce qui a été fait**

* Dix formulaires réels ont été vérifiés à la main, puis relus par l'IA.
* **Résultat : 95,7 % des valeurs bien lues.** Un second test identique a donné 94,7 % : un écart d'environ 1 point est donc normal.
* Ces tests ont révélé des défauts dans la liste des champs et dans la façon de compter les erreurs. Ils ont été corrigés.
* Des consignes plus détaillées pour l'IA ont été essayées. Le résultat était moins bon (93,7 %), elles n'ont pas été retenues.

**Pourquoi c'est important**
C'est la première mesure sur de vrais formulaires. Elle montre qu'il faut comprendre une erreur avant d'en accuser l'IA.

---

### À venir

* Faire vérifier ces formulaires par trois opérateurs, pour une référence plus fiable.
* Mettre en service la page des métriques.
* Tester un second moteur de lecture pour comparer.
