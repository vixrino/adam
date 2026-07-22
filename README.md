# ADAM - Annotation et Données Automatisées

> Branche `master` ne contient pas encore de release stable. Le développement actif se trouve sur la branche `develop`.

## Accéder au code

```bash
git clone https://git.example.com/example-org/adam/adam.git
cd adam
git checkout develop
```

## Branches

| Branche | Rôle |
| :--- | :--- |
| `main` | Releases stables uniquement |
| `develop` | Développement actif |
| `feature/*` | Nouvelles fonctionnalités |
| `fix/*` | Corrections de bugs |

## Contact

import x_core.models
from x_core.db.scoping import _iter_scoped_models
from x_core.models import (
    Dataset, DocSchema, Document, DocumentField, FieldProposal,
    FieldSpec, Job, OcrResult, UserProject,
)

scoped = set(_iter_scoped_models())
expected = {
    Dataset, DocSchema, Document, DocumentField, FieldProposal,
    FieldSpec, Job, OcrResult, UserProject,
}
print("MANQUANTS :", sorted(m.__name__ for m in expected - scoped))
print("SCOPES    :", sorted(m.__name__ for m in scoped))
