# Helper _unlocked_db — REMPLACE integralement la version precedente.
#
# La version precedente posait un bouchon unique, que deux requetes
# consommaient : la verification du verrou, puis la recuperation du schema.
# La premiere voyait l'objet destine a la seconde, le trouvait vrai, et
# concluait au verrou — d'ou les 409 sur add / patch / delete de field-specs.
#
# Ici le premier execute() est traite a part : il ne trouve rien, donc pas de
# dataset actif, donc pas de verrou. Les suivants retombent sur le resultat
# bouchonne par la fixture, que le test a pu regler pour ses propres besoins.


def _unlocked_db(mock_db: AsyncMock) -> AsyncMock:
    """Simule un schema non verrouille sans consommer le bouchon des requetes suivantes."""
    normal = mock_db.execute.return_value

    not_locked = MagicMock()
    not_locked.scalar_one_or_none.return_value = None
    not_locked.scalar_one.return_value = 0
    not_locked.scalar.return_value = None
    not_locked.one_or_none.return_value = None
    not_locked.first.return_value = None
    not_locked.scalars.return_value.all.return_value = []
    not_locked.scalars.return_value.first.return_value = None

    calls = {"n": 0}

    async def _exec(*args: object, **kwargs: object) -> MagicMock:
        calls["n"] += 1
        return not_locked if calls["n"] == 1 else normal

    mock_db.execute.side_effect = _exec
    return mock_db
