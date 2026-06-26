"""
Point d'entree DEV uniquement.
Usage: python scripts/run_dev.py
"""
import uvicorn

from adam_api.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "adam_api.main:app",
        host="127.0.0.1",
        port=settings.api_port,
        reload=True,
        log_config=None,
        access_log=False,
    )
