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
Chaque utilisateur ne voit plus que les données de son organisation et des projets auxquels il est affecté. Lesateur, administrateur métier…) sont séparés des rôles sur la plateforme (administrateur technique).                
Autres points livrés :                                                              
* Un traitement automatique qui suit en continu l'avancement de chaque document et  le fait passer à l'étape suion « en continu » annoncéeplus haut.                                                                          * Un traitement automatique d'un document dès son arrivée, pour que l'opérateur n'ait plus qu'à vérifier.                                      * Le premier raccordement à ntelligence artificielle(Mistral), qui lit chaque page et propose une valeur pour chaque champ.             * Le modèle de données des fla lecture.
* Un guide de sécurité qui explique comment l'authentification est branchée et ce   qu'il reste à faire.
                                                                                    **Pourquoi c'est important**
Sans cette étape, l'application ne pouvait pas être ouverte à de vrais agents : il  fallait d'abord savoir qui sue chacun voit. Lepréremplissage par l'IA est aussi le premier pas vers le vrai gain de temps attendu : vérifier au lieu de ressai
                                                                                    ---
                                                                                    ### Endettement complet
                                                                                    **Ce qui a été fait**
La liste complète des champs du formulaire officiel de surendettement (12 pages) a  été décrite dans l'applicatimparant à des formulairesréels.                                                                              La lecture par l'IA a été ne
                                                                                    * l'IA reconnaît d'abord de il s'agit, même si les pagesont été scannées dans le désordre, puis remet le document dans le bon ordre ;       * elle ne confond plus le teavec les réponses de lapersonne ;                                                                          * elle distingue une case vi
* elle n'est plus programmée pour un seul formulaire : elle suit la liste des champsdu lot de documents, ce qui utres types de documents.
                                                                                    Autres points livrés :
                                                                                    * Un document trop volumineupas le bon formulaire est misde côté avec un message d'erreur clair.                                             * Un lot de documents suit m: brouillon, actif, archivé.
* Un administrateur peut affecter une personne de l'annuaire à un projet avant même sa première connexion.
* L'application et tous ses traitements automatiques se lancent en une seule        commande.
                                                                                    **Pourquoi c'est important**
C'est cette étape qui adapte l'outil au vrai besoin métier : le formulaire de       surendettement tel que les aes pages parfois mélangées oumal remplies.                                                                       
---                                                                                 
### MTableaux du formulaire et outil de mesure de  la qualité
                                                                                    **Ce qui a été fait**
L'IA lit maintenant chaque ligne des tableaux du formulaire (liste des crédits, des dettes, des personnes à chars champs isolés. Les prêts àla consommation n° 7 et 8 de la page 11 ont été ajoutés.                             Un outil de test a été constl'IA des documents déjàvérifiés par des agents, puis compare les deux réponses champ par champ. Il en tire  des indicateurs simples, comn lues et la part des valeurstrouvées.                                                                           
**Pourquoi c'est important**                                                         Jusqu'ici, on ne pouvait jug quelques exemples. Cet outildonne une mesure chiffrée et répétable de la qualité de la lecture : c'est ce qui    permettra de décider, preuverête pour la production et decomparer deux moteurs entre eux.                                                    
---                                                                                 
### Page des métriques et tests fiables                              
**Ce qui a été fait**                                                                Côté backend, la page des mésultats d'un test peuvent être filtrés par page, par rubrique ou par type de champ, consultés champ par champ et    exportés en rapport PDF, à lretenue.
L'outil de test a été rendu plus fiable :                                           
* un test se fait toujours sur une copie figée des documents vérifiés, pour que deux tests soient vraiment compar
* l'outil refuse de comparer deux tests qui n'ont pas été faits dans les mêmes       conditions ;
* seul un administrateur peut modifier les consignes données à l'IA ;                * on peut suivre l'avancemenn cours de route.
                                                                                     Une relecture complète a perts avant la mise en service.
                                                                                     **Pourquoi c'est important**
Un chiffre n'a de valeur que si on peut lui faire confiance. Ces garanties évitent   de conclure à une améliorati l'IA à partir de tests qui ne seraient pas comparables.                                                           
---                                                                                 
### Premiers tests sur de vrais formulaires                  
**Ce qui a été fait**                                                                L'outil de test a été lancé,r dix formulaires réelsvérifiés à la main.                                                                 
* **Premier test, sur un formulaire :** 97 valeurs sur 101 bien lues. 2 des 4        erreurs venaient de la listeElles ont été corrigées.
* **La vérification des dix formulaires** a fait apparaître d'autres défauts de la   liste des champs. Ils ont étpuis le » par situationprofessionnelle, l'ordre des rubriques aligné sur le formulaire papier, une mention  imprimée qui n'est plus priscuments déjà vérifiés ont étéconvertis sans perdre le travail des agents.                                         * **Un score qui baissait saré :** le score est passé de95,3 % à 87,9 %, parce que l'outil comptait comme des fautes de simples différences  de présentation (une virguleare désormais les lettres etles chiffres sans tenir compte de la ponctuation. Deux erreurs de calcul ont aussi   été corrigées.
* **Résultat sur les dix formulaires : 95,7 %** de valeurs bien lues et trouvées.    * **Un second test identique répond pas exactement pareilà chaque passage : un écart d'environ 1 point ne prouve donc rien.                   * **Des consignes enrichies der l'IA à corriger ses fautes (par exemple « PRANCE » → « FRANCE »). Résultat moins bon (93,7 %) : l'IA «          corrigeait » des valeurs jusenues.
                                                                                     **Pourquoi c'est important**
C'est la première mesure de la qualité de l'IA sur de vrais formulaires. Elle montre aussi qu'il faut comprendre cuser l'IA : plusieursbaisses venaient de la liste des champs ou de la façon de compter, pas de la lecture.

---
