"""Table FILE : fichier physique stocké sur PVC.

Un enregistrement FILE est unique par contenu.
Plusieurs DOCUMENT peuvent référencer le même FILE.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base


class File(Base):
    __tablename__ = "file"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Chemin absolu sur FS",
    )
    storage_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="pvc",
        comment="Backend de stockage",
    )
    mime_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="application/pdf",
    )
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Taille en octets pour le calcul de volumétrie",
    )
    # Clé de déduplication physique
    sha256_checksum: Mapped[str] = mapped_column(
        String,
        nullable=False,
        unique=True,
        index=True,
        comment="Empreinte SHA-256 : unicité physique + intégrité",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Date de première ingestion",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    documents: Mapped[list["Document"]] = relationship(  # type: ignore[name-defined]
        "Document",
        back_populates="file",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<File id={self.id} "
            f"sha256={self.sha256_checksum[:12]!r}... "
            f"pages={self.page_count} "
            f"storage={self.storage_type!r} "
            f"size={self.file_size_bytes} bytes>"
        )
