# Export du test d'ingestion pour NOTA

Fichier a copier TEL QUEL (imports deja renommes nota_*) — ne pas retaper :

    tests_unit/test_service_ingestion.py  -> tests/unit/test_service_ingestion.py

Cette copie REMPLACE integralement la version precedente cote NOTA.

## Pourquoi

Le helper s'appelle `get_or_create_file` cote NOTA et s'appelait
`_get_or_create_file` cote ADAM, pour un corps identique. Le fichier de test
circulant d'un depot a l'autre, il echouait a la collecte cote NOTA sur un
`ImportError: cannot import name '_get_or_create_file'` — une erreur qui
laissait croire a une fonction supprimee alors qu'elle etait renommee.

ADAM est desormais aligne sur la forme NOTA (commit dacf21b) : la fonction y
est publique elle aussi, et les deux depots portent le meme fichier de test a
l'espace de noms pres.

Ne pas tenter le renommage par un rechercher-remplacer PowerShell : deux
tentatives ont supprime le nom au lieu de le remplacer, laissant `await (`
en lieu et place de l'appel et un `SyntaxError` a la collecte. Copier le
fichier entier est plus sur.

## Aucune retouche a la main

`src/nota_api/services/ingestion.py` est deja dans la bonne forme cote NOTA :
c'est le test qui etait en retard, pas le service. Ne rien y changer.

## Verification

    uv run python -m py_compile tests/unit/test_service_ingestion.py
    uv run pytest tests/unit/test_service_ingestion.py -v

15 tests attendus.
