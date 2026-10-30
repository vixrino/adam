"""
Tests unitaires adam_core/db/session.py
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from adam_core.db import session as session_module
from adam_core.db.session import (
    DatabaseUnavailable,
    check_database,
    ensure_database,
    get_engine,
    init_engine,
)

# Fixtures


@pytest.fixture(autouse=True)
def reset_engine() -> None:
    """Remet le module dans un etat propre entre chaque test."""
    session_module._engine = None
    session_module._async_session_factory = None
    yield
    session_module._engine = None
    session_module._async_session_factory = None


# init_engine


class TestInitEngine:
    def test_engine_is_set_after_init(self) -> None:
        with (
            patch("adam_core.db.session.create_async_engine") as mock_engine,
            patch("adam_core.db.session.async_sessionmaker"),
        ):
            mock_engine.return_value = MagicMock()
            init_engine("postgresql+asyncpg://user:pass@localhost/db")
            assert session_module._engine is not None

    def test_session_factory_is_set_after_init(self) -> None:
        with (
            patch("adam_core.db.session.create_async_engine"),
            patch("adam_core.db.session.async_sessionmaker") as mock_factory,
        ):
            mock_factory.return_value = MagicMock()
            init_engine("postgresql+asyncpg://user:pass@localhost/db")
            assert session_module._async_session_factory is not None

    def test_echo_passed_to_engine(self) -> None:
        with (
            patch("adam_core.db.session.create_async_engine") as mock_engine,
            patch("adam_core.db.session.async_sessionmaker"),
        ):
            init_engine("postgresql+asyncpg://user:pass@localhost/db", echo=True)
            _, kwargs = mock_engine.call_args
            assert kwargs["echo"] is True

    def test_url_stripped_of_credentials_in_log(self, caplog: pytest.LogCaptureFixture) -> None:
        with (
            patch("adam_core.db.session.create_async_engine"),
            patch("adam_core.db.session.async_sessionmaker"),
            caplog.at_level("INFO", logger="adam_core.db.session"),
        ):
            init_engine("postgresql+asyncpg://user:secret@localhost:5432/nota_db")
            assert "secret" not in caplog.text
            assert "localhost:5432/nota_db" in caplog.text


# get_engine


class TestGetEngine:
    def test_raises_if_not_initialized(self) -> None:
        with pytest.raises(RuntimeError, match="init_engine"):
            get_engine()

    def test_returns_engine_after_init(self) -> None:
        with (
            patch("adam_core.db.session.create_async_engine") as mock_engine,
            patch("adam_core.db.session.async_sessionmaker"),
        ):
            mock_engine.return_value = MagicMock()
            init_engine("postgresql+asyncpg://user:pass@localhost/db")
            assert get_engine() is session_module._engine


# get_async_session


class TestGetAsyncSession:
    @pytest.mark.asyncio
    async def test_raises_if_factory_not_initialized(self) -> None:
        from adam_core.db.session import get_async_session

        with pytest.raises(RuntimeError, match="Session factory"):
            async with get_async_session() as _:
                pass

    @pytest.mark.asyncio
    async def test_commits_on_success(self) -> None:
        from adam_core.db.session import get_async_session

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_cm)
        session_module._async_session_factory = mock_factory
        async with get_async_session() as _:
            pass
        mock_session.commit.assert_awaited_once()


# check_database / ensure_database

_URL_INJOIGNABLE = "postgresql+asyncpg://nota:motdepasse-secret@127.0.0.1:1/nota_db"


class TestInitEngineErreurs:
    def test_url_invalide_ne_divulgue_pas_le_mot_de_passe(self) -> None:
        with pytest.raises(DatabaseUnavailable) as err:
            init_engine("pas-une-url:motdepasse-secret")
        assert "motdepasse-secret" not in str(err.value)
        assert err.value.__cause__ is None

    def test_pilote_manquant(self) -> None:
        with patch(
            "adam_core.db.session.create_async_engine",
            side_effect=ModuleNotFoundError(name="asyncpg"),
        ):
            with pytest.raises(DatabaseUnavailable, match="asyncpg"):
                init_engine("postgresql+asyncpg://u:p@localhost/db")


class TestCheckDatabase:
    async def test_ok_quand_la_base_repond(self) -> None:
        conn = AsyncMock()
        engine = MagicMock()
        engine.connect.return_value.__aenter__ = AsyncMock(return_value=conn)
        engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)
        session_module._engine = engine
        await check_database()
        conn.execute.assert_awaited_once()

    async def test_base_arretee_leve_sans_divulguer_le_mot_de_passe(self) -> None:
        init_engine(_URL_INJOIGNABLE)
        with pytest.raises(DatabaseUnavailable) as err:
            await check_database(timeout=2)
        message = str(err.value)
        assert "motdepasse-secret" not in message
        assert "127.0.0.1" in message and "nota_db" in message

    async def test_delai_depasse(self) -> None:
        engine = MagicMock()
        engine.url.render_as_string.return_value = "postgresql+asyncpg://nota:***@h/db"
        engine.connect.side_effect = TimeoutError()
        session_module._engine = engine
        with pytest.raises(DatabaseUnavailable, match="TimeoutError"):
            await check_database()


class TestCheckDatabaseMauvaisMotDePasse:
    async def test_erreur_brute_du_pilote_est_convertie(self) -> None:
        """asyncpg leve InvalidPasswordError tel quel : ni SQLAlchemyError ni OSError."""

        class InvalidPasswordError(Exception):
            pass

        engine = MagicMock()
        engine.url.render_as_string.return_value = "postgresql+asyncpg://nota:***@h/db"
        engine.connect.side_effect = InvalidPasswordError('mot de passe de "nota" refuse')
        session_module._engine = engine
        with pytest.raises(DatabaseUnavailable, match="InvalidPasswordError") as err:
            await check_database()
        assert err.value.__cause__ is None


class TestEnsureDatabase:
    async def test_arret_avec_code_1_et_message_clair(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        init_engine(_URL_INJOIGNABLE)
        with caplog.at_level("CRITICAL", logger="adam_core.db.session"):
            with pytest.raises(SystemExit) as exit_info:
                await ensure_database()
        assert exit_info.value.code == 1
        assert "Base injoignable" in caplog.text
        assert "motdepasse-secret" not in caplog.text
