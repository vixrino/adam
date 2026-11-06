# ADAM - Annotation et Données Automatisées

#: 1
Tâche: Créer le PDF et le tester
Qui: Lucas
Jours: 4,5
Description: Nouvelle adresse dans le back qui renvoie le PDF des métriques d'un test. Le PDF contient :<br>• le haut : score, résultat
  réussi ou raté, alertes<br>• les tableaux détaillés : par type de champ, par section et par importance<br>• la liste des champs mal
  lus<br>Il est fabriqué avec PyMuPDF, déjà installé.<br>Tests : le PDF s'ouvre, un test pas encore fini renvoie une erreur claire, et
  aucune donnée personnelle (IBAN, nom…) n'y apparaît.<br>Essai final sur un vrai document de 642 champs, pour vérifier la longueur et les
  sauts de page.
────────────────────────────────────────
#: 2
Tâche: Mettre le code du PDF dans nota
Qui: Lucas
Jours: 1
Description: Copier les fichiers d'adam vers nota en renommant adam_* en nota_*, puis relancer les tests dans nota.
────────────────────────────────────────
#: 3
Tâche: Créer la page et afficher toutes les infos
Qui: Daniel
Jours: 4,5
Description: Nouvelle page qui affiche les métriques d'un test, à partir de ce que renvoie déjà le back.<br>• En haut : score, nombre de
  valeurs justes, fausses, oubliées et inventées, résultat réussi ou raté, alertes (par exemple « pas assez de documents »)<br>• Au milieu :
   les tableaux par type de champ, par section et par importance<br>• En bas : la liste des champs mal lus, les pires en premier
────────────────────────────────────────
#: 4
Tâche: Bouton PDF et cas particuliers
Qui: Daniel
Jours: 1,5
Description: Bouton « Télécharger le PDF » qui récupère le fichier fabriqué par le back.<br>Affichage prévu pour chaque cas :<br>• pas de
  données<br>• chargement en cours<br>• test pas encore fini<br>• erreur du serveur
────────────────────────────────────────
#: 5
Tâche: Tester la page
Qui: Daniel
Jours: 1
Description: Tests automatiques du front (Jest) : la page affiche les bonnes valeurs, le bouton télécharge bien le PDF, et chaque cas
  particulier s'affiche correctement.
────────────────────────────────────────
#: 6
Tâche: Tester tout ensemble sur nota
Qui: Lucas + Daniel
Jours: 2 chacun
Description: Lancer un vrai test OCR sur nota, ouvrir la page, télécharger le PDF et vérifier que la page et le PDF montrent les mêmes
  chiffres. Corriger ce qui ne va pas.

Total :
- Lucas : 7,5 jours sur 12 disponibles ;
- Daniel : 9 jours sur 12 disponibles.
