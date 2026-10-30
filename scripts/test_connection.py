"""
Script standalone pour vérifier la connexion à PostgreSQL.
"""

import asyncio
import os
import sys
from pathlib import Path


# Chargement du .env
def load_env(env_path: Path = Path(".env")) -> None:
    if not env_path.exists():
        print(f"[WARN] Fichier {env_path} introuvable : utilisation des variables système")
        return
    with env_path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


load_env()

# Paramètres de connexion
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_HOST = os.getenv("POSTGRES_HOST")
DB_PORT = int(os.getenv("POSTGRES_PORT"))
DB_NAME = os.getenv("POSTGRES_DB")


async def test_connection() -> bool:
    try:
        import asyncpg
    except ImportError:
        print("[ERROR] asyncpg n'est pas installé.")
        return False

    url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    print(f"URL: {url}")
    print(f"\n  Tentative de connexion sur :")
    print(f"  host={DB_HOST}  port={DB_PORT}  db={DB_NAME}  user={DB_USER}\n")

    try:
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            timeout=5,
        )
    except Exception as e:
        print(f"  [ÉCHEC] Impossible de se connecter :\n  {type(e).__name__}: {e}")
        print("\n  Vérifications :")
        print("  1. PostgreSQL est-il démarré ? (Services Windows → postgresql-x64-14)")
        print("  2. Le user 'nota' existe-t-il dans pgAdmin ?")
        print("  3. La base 'nota_db' existe-t-elle avec owner='nota' ?")
        print("  4. Les credentials dans .env sont-ils corrects ?")
        return False

    # Requêtes de vérification
    pg_version = await conn.fetchval("SELECT version()")
    current_db = await conn.fetchval("SELECT current_database()")
    current_user = await conn.fetchval("SELECT current_user")

    await conn.close()

    print(f"  [OK] Connexion réussie !")
    print(f"  PostgreSQL : {pg_version.split(',')[0]}")
    print(f"  Base       : {current_db}")
    print(f"  Utilisateur: {current_user}")
    return True


if __name__ == "__main__":
    print("=" * 55)
    print("Test de connexion PostgreSQL")
    print("=" * 55)
    success = asyncio.run(test_connection())
    print("=" * 55)
    sys.exit(0 if success else 1)
