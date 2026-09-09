# Seed nota — fichier pret a copier

`scripts/seed.py` de ce repertoire remplace celui de nota-back tel quel. Aucun
renommage a faire : les imports sont deja en `nota_core`.

## Ce qui change

Quatre points, ceux demandes, et rien d'autre.

| Zone | Avant | Apres |
|---|---|---|
| Organisations | DGRH et DIRES, une seule peuplee | les deux peuplees |
| Utilisateurs | `Admin NOTA`, `Operateur NOTA` | sept agents nommes |
| Projets | un seul, dans DGRH | un projet type par organisation |
| Lots | `Lot janvier 2026`, `Lot CERFA Surendettement - Seed` | `cerfa_13594-02_v2` |

Les matricules `V654846`, `I659418` et `MAT00003` gardent leurs valeurs et leurs
roles : le mock FBI, `check_project_scoping.py` et la valeur par defaut
d'`API_DEV_MATRICULE` s'appuient dessus.

## Ce qui ne change pas

`file_path`, les dates 2026, `HARDCODED_FIELD_SPECS` avec ses `required` et ses
`polygon`, `HARDCODED_OCR_VALUES`, les noms de `DocSchema`, les descriptions de
lot, `metadata_`, `hashlib` — a l'identique.

## Verification

Execute contre une base PostgreSQL reelle, en redirigeant `nota_core` vers
`adam_core` — les deux paquets ne different que par leur prefixe.

```
 slug  | agents | projets
-------+--------+---------
 dgrh  |      4 |       1
 dires |      3 |       1
```

Le `file_path` et le `metadata` du document ressortent inchanges en base :

```
/pvc/DIRES/cerfa/2026_01/2026_01_15_1321/cerfa_13594_sample.pdf
{"lot": "2026-01", "source": "PVC", "reception_date": "2026-01-15"}
```

## Un defaut a connaitre, cote adam seulement

Le seed d'adam construit ses documents avec `metadata=`, alors que l'attribut
mappe s'appelle `metadata_`. Le constructeur declaratif ne proteste pas :
`metadata` existe deja sur la classe, c'est l'objet `MetaData` de SQLAlchemy.
La valeur est donc posee sur l'instance, ou elle masque cet objet, et la colonne
reste NULL.

```python
d = Document(..., metadata={"source": "PVC"})
d.metadata_   # None — rien n'est persiste
```

Le fichier de ce repertoire utilise `metadata_`, comme nota : il n'est pas
concerne.
