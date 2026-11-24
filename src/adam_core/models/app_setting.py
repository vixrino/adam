"""Table APP_SETTING : configuration modifiable a chaud (flags, delais des workers).

Cle -> valeur JSON. Lue a chaque cycle par les workers, a la demande par l'API :
aucun cache, donc aucune invalidation. Les secrets, l'infra et les flags de
securite restent dans l'environnement.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from adam_core.db.base import Base


class AppSetting(Base):
    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    updated_by: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, comment="Matricule de l'auteur de la derniere modification"
    )
