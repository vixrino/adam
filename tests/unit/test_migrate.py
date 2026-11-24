"""adam_core/db/migrate.py et chaine de migrations (sans base de donnees)."""

from unittest.mock import patch

import pytest
from alembic.script import ScriptDirectory

from adam_core.db import migrate


def test_upgrade_head_applies_head() -> None:
    with patch("adam_core.db.migrate.command.upgrade") as upgrade:
        migrate.upgrade_head()
    config, revision = upgrade.call_args.args
    assert revision == "head"
    assert config.config_file_name == str(migrate.ALEMBIC_INI)


def test_upgrade_head_exits_1_on_failure(caplog: pytest.LogCaptureFixture) -> None:
    with patch("adam_core.db.migrate.command.upgrade", side_effect=RuntimeError("boom")):
        with pytest.raises(SystemExit) as exc:
            migrate.upgrade_head()
    assert exc.value.code == 1
    assert "RuntimeError" in caplog.text


def test_migration_chain_has_a_single_head() -> None:
    """Deux heads = deux branches non fusionnees : `upgrade head` refuserait de choisir."""
    heads = ScriptDirectory.from_config(migrate.alembic_config()).get_heads()
    assert len(heads) == 1
