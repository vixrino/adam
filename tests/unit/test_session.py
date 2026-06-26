import pytest

from adam_core.db.session import get_engine, init_engine


def test_init_engine_requires_url() -> None:
    init_engine("postgresql+asyncpg://u:p@localhost:5432/db")
    assert get_engine() is not None
