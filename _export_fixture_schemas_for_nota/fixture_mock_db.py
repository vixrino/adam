# Fixture mock_db — REMPLACE integralement la fixture du meme nom
# (bloc complet, `return db` compris)

@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock(side_effect=lambda obj: setattr(obj, "id", 1))
    db.add_all = MagicMock()
    result = MagicMock()
    # Tous les accesseurs de resultat sont bouchonnes, pas seulement ceux que
    # les routes utilisent aujourd'hui. Un accesseur oublie rend un MagicMock,
    # qui est vrai : une route qui cherche un doublon croit alors en trouver un,
    # et le test echoue en 409 sur une ligne qui n'existe pas.
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = None
    result.scalars.return_value.one_or_none.return_value = None
    result.scalar_one_or_none.return_value = None
    result.scalar_one.return_value = None
    result.one_or_none.return_value = None
    result.first.return_value = None
    result.scalar.return_value = None
    db.execute.return_value = result
    db.get.return_value = None
    return db


# Helper _unlocked_db — A AJOUTER, juste avant la premiere classe de test

def _unlocked_db(mock_db: AsyncMock) -> AsyncMock:
    """Configure le mock pour simuler un schema non verrouille et sans DocumentFields."""
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    mock_db.execute.return_value.scalar_one.return_value = 0
    return mock_db
