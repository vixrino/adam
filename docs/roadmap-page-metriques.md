# Roadmap : page des métriques et export PDF

Échéance : **24 novembre 2026**. Équipe : Lucas (back), Daniel (front).
12 jours ouvrés du 6 au 24 novembre (le 11 est férié).

Choix retenu : le PDF est fabriqué par le back, avec PyMuPDF (déjà installé).

| # | Tâche | Qui | Jours |
|---|---|---|---|
| 1 | Créer le PDF et le tester | Lucas | 4,5 |
| 2 | Mettre le code du PDF dans nota | Lucas | 1 |
| 3 | Créer la page et afficher toutes les infos | Daniel | 4,5 |
| 4 | Bouton PDF et cas particuliers | Daniel | 1,5 |
| 5 | Tester la page | Daniel | 1 |
| 6 | Tester tout ensemble sur nota | Lucas + Daniel | 2 chacun |

**Total :** Lucas 7,5 jours, Daniel 9 jours, sur 12 disponibles.

## 1. Créer le PDF et le tester — Lucas, 4,5 j

Nouvelle adresse dans le back qui renvoie le PDF des métriques d'un test.

Contenu du PDF :
- le haut : score, résultat réussi ou raté, alertes ;
- les tableaux détaillés : par type de champ, par section, par importance ;
- la liste des champs mal lus.

Tests :
- le PDF s'ouvre ;
- un test pas encore fini renvoie une erreur claire ;
- aucune donnée personnelle (IBAN, nom…) n'apparaît.

Essai final sur un vrai document de 642 champs : longueur et sauts de page.

## 2. Mettre le code du PDF dans nota — Lucas, 1 j

Copier les fichiers d'adam vers nota (renommer `adam_*` en `nota_*`), puis
relancer les tests dans nota.

## 3. Créer la page et afficher toutes les infos — Daniel, 4,5 j

Nouvelle page qui affiche les métriques d'un test, à partir de
`GET /test-executions/{id}/metriques` (déjà prêt côté back).

- En haut : score, nombre de valeurs justes, fausses, oubliées, inventées,
  résultat réussi ou raté, alertes (ex. « pas assez de documents ») ;
- au milieu : tableaux par type de champ, par section, par importance ;
- en bas : liste des champs mal lus, les pires en premier.

## 4. Bouton PDF et cas particuliers — Daniel, 1,5 j

Bouton « Télécharger le PDF » qui récupère le fichier fabriqué par le back.

Affichage prévu pour chaque cas : pas de données, chargement en cours, test
pas encore fini, erreur du serveur.

## 5. Tester la page — Daniel, 1 j

Tests Jest : la page affiche les bonnes valeurs, le bouton télécharge le PDF,
chaque cas particulier s'affiche correctement.

## 6. Tester tout ensemble sur nota — Lucas + Daniel, 2 j chacun

Lancer un vrai test OCR sur nota, ouvrir la page, télécharger le PDF, vérifier
que la page et le PDF montrent les mêmes chiffres. Corriger ce qui ne va pas.
