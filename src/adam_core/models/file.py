"""Table FILE : fichier physique stocke sur FS."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base


class File(Base):
    __tablename__ = "file"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    storage_type: Mapped[str] = mapped_column(String, nullable=False, default="pvc")
    mime_type: Mapped[str] = mapped_column(String, nullable=False, default="application/pdf")
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    documents: Mapped[list["Document"]] = relationship("Document", back_populates="file", lazy="noload")

    def __repr__(self) -> str:
        return f"<File id={self.id} path={self.file_path!r} sha256={self.sha256_checksum[:8]}...>"
