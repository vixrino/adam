"""Test de connexion PostgreSQL async."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import text

from adam_core.core.config import get_core_settings
from adam_core.db.session import get_async_session, init_engine


async def test_connection() -> bool:
    settings = get_core_settings()
    init_engine(settings.async_database_url)
    async with get_async_session() as session:
        result = await session.execute(text("SELECT 1"))
        val = result.scalar_one()
        print(f"Connexion OK (SELECT 1 -> {val})")
        return val == 1


if __name__ == "__main__":
    print("=" * 55)
    print(" ADAM - Test connexion PostgreSQL")
    print("=" * 55)
    success = asyncio.run(test_connection())
    print("=" * 55)
    sys.exit(0 if success else 1)
