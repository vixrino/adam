# Report vers nota : T7, pymupdf, worker de tests batch

`changements.patch` = tout ce que `feature/worker-tests-batch` change par
rapport a `main` d'adam (22 fichiers), avec `adam_*` deja renomme en `nota_*`.

Verifie : applique sur une copie de `main` aux paquets renommes, les 797 tests
passent.

## Appliquer (depuis la racine de nota-back, sur ta branche)

    git apply --check changements.patch      # 1. dit si tout passe, n'ecrit rien
    git apply changements.patch              # 2a. si --check est muet
    git apply --reject changements.patch     # 2b. sinon : applique ce qui passe

`--reject` ecrit un `<fichier>.rej` pour chaque morceau qui ne s'applique pas
(fichier nota qui a diverge d'adam) : reporter ces morceaux a la main, puis
supprimer les `.rej`.

## Ensuite

- `.env` : `COMPARISON_HMAC_KEY=` (python -c "import secrets; print(secrets.token_hex(32))")
- `uv run --all-extras pytest`
