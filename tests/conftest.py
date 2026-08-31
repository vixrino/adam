"""Valeurs de repli pour les tests, posees uniquement si aucun .env n'existe.

Le garde-fou sur le .env est indispensable : pydantic-settings donne la
priorite aux variables d'environnement SUR le fichier .env, donc les poser
sans condition ecraserait la configuration reelle du poste de dev.
"""

import os
from pathlib import Path

if not (Path(__file__).resolve().parent.parent / ".env").exists():
    # App
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("APP_NAME", "NOTA")
    os.environ.setdefault("APP_VERSION", "0.1.0")

    # PostgreSQL (aucune connexion reelle dans les tests unitaires)
    os.environ.setdefault("POSTGRES_USER", "nota")
    os.environ.setdefault("POSTGRES_PASSWORD", "test")
    os.environ.setdefault("POSTGRES_HOST", "localhost")
    os.environ.setdefault("POSTGRES_PORT", "5432")
    os.environ.setdefault("POSTGRES_DB", "nota_db")

    # API
    os.environ.setdefault("API_HOST", "127.0.0.1")
    os.environ.setdefault("API_PORT", "8000")
    os.environ.setdefault("API_VERSION", "0.1.0")
    os.environ.setdefault("API_TITLE", "NOTA API")
    os.environ.setdefault("API_CORS_ORIGINS", "http://localhost")
    os.environ.setdefault("API_DISABLE_JWT_VALIDATION", "true")
    os.environ.setdefault("API_DEV_MATRICULE", "MAT00003")

    # Auth service machine
    os.environ.setdefault("INTERNAL_AUTH_ENABLED", "false")
    os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")

    # JWT
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
    os.environ.setdefault("JWT_ALGORITHM", "HS256")
    os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")

    # Stockage fichiers
    os.environ.setdefault("PVC_MOUNT_PATH", "./data/pvc")

    # Logging
    os.environ.setdefault("LOG_LEVEL", "DEBUG")
    os.environ.setdefault("LOG_FORMAT", "text")

    # OCR
    os.environ.setdefault("OCR_MOCK_ENABLED", "true")
    os.environ.setdefault("OCR_MOCK_CONFIDENCE", "0.95")
    os.environ.setdefault("OCR_TIMEOUT_SECONDS", "30")
