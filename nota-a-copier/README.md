# Fichiers à copier dans nota-back

Chaque fichier se copie à **la même place** dans `C:\DEV\nota-back`, sans le préfixe `nota-a-copier/`. Il remplace le fichier existant en entier.

Ces fichiers partent de l'export nota du 23/11 (`8107c30`). Avant de remplacer un fichier, vérifie qu'il n'a pas changé depuis cet export : la commande ci-dessous ne doit rien afficher.

```powershell
git diff 8107c30 -- src/nota_worker/connectors/mistral.py tests/unit/test_connector_mistral.py
```

| Fichier | Modification |
|---|---|
| `src/nota_worker/connectors/mistral.py` | `_identification_instruction` : le nom du schéma devient une étiquette interne, et le nombre de pages un minimum (MR #43) |
| `tests/unit/test_connector_mistral.py` | deux assertions mises à jour, plus le test `test_le_nom_du_schema_n_est_qu_une_etiquette` |
