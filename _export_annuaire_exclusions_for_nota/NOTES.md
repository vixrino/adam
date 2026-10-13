# Report vers nota : exclusion des comptes OT2 de l'annuaire

Deux patchs, `adam_*` deja renomme en `nota_*` :

- `changements.patch` : tout (prefixes, fins de matricule, unites
  d'organisation). A prendre si rien n'a encore ete applique.
- `complement_suffixes.patch` : seulement l'exclusion par fin de matricule,
  si le premier patch (prefixes et unites) est deja applique.

    git apply --check <patch>
    git apply <patch>

Puis dans le .env : `AD_EXCLUDE_SUFFIXES=OT2`, et redemarrer l'API.
