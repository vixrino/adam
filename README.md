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


from x_worker.base_worker import BaseWorker


class ConsensusWorker(BaseWorker):
    """Relance la resolution du consensus sur les documents en attente."""

    async def poll(self) -> None:
        await run_pending_consensus()
