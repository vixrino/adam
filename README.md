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

- Développeur : dev@example.com

1. Imports à ajouter en haut du fichier (si pas déjà présents) :
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse
from nota_api.core.config import settings

2. Insère cette fonction entre get_file et get_file_documents :
@router.get("/{file_id}/content")
async def get_file_content(file_id: int, db: AsyncSession = Depends(get_db)) -> FileResponse:
    """Retourne les octets bruts du fichier physique (PDF), pour visualisation/telechargement."""
    file = await db.get(File, file_id)
    if not file:
        raise_not_found(File)
    abs_path = Path(settings.pvc_mount_path) / file.file_path
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="Fichier absent du PVC")
    return FileResponse(abs_path, media_type=file.mime_type, filename=abs_path.name)
