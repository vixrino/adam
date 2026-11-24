"""La base est partagee entre applications : tout ce que nota cree vit dans son schema."""

from unittest.mock import AsyncMock, MagicMock, patch

from adam_core.db import session as session_module
from adam_core.db.base import SCHEMA_NAME, Base
import adam_core.models  # noqa: F401  (enregistre les tables dans Base.metadata)


class TestMetadata:
    def test_schema_est_nota(self) -> None:
        assert SCHEMA_NAME == "nota"

    def test_toutes_les_tables_sont_dans_le_schema(self) -> None:
        assert {t.schema for t in Base.metadata.tables.values()} == {SCHEMA_NAME}

    def test_les_cles_etrangeres_visent_le_schema(self) -> None:
        cibles = {
            fk.column.table.schema
            for table in Base.metadata.tables.values()
            for fk in table.foreign_keys
        }
        assert cibles == {SCHEMA_NAME}


class TestCreateTables:
    async def test_cree_le_schema_avant_les_tables(self) -> None:
        conn = AsyncMock()
        engine = MagicMock()
        engine.begin.return_value.__aenter__ = AsyncMock(return_value=conn)
        engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
        session_module._engine = engine
        with patch.object(session_module, "get_engine", return_value=engine):
            await session_module.create_tables()

        creation = conn.execute.await_args.args[0]
        assert str(creation) == f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA_NAME}"'
        conn.run_sync.assert_awaited_once_with(Base.metadata.create_all)
        # Le schema d'abord, sinon create_all echoue sur une base neuve.
        appels = [c[0] for c in conn.method_calls]
        assert appels.index("execute") < appels.index("run_sync")
