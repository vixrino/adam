"""Table PROJECT : unite de travail rattachee a une organisation."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.enums.status import ProjectStatus


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organisation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organisation.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default=ProjectStatus.ACTIVE.value)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    organisation: Mapped["Organisation"] = relationship(
        "Organisation", back_populates="projects", lazy="noload"
    )
    datasets: Mapped[list["Dataset"]] = relationship("Dataset", back_populates="project", lazy="noload")
    schemas: Mapped[list["DocSchema"]] = relationship("DocSchema", back_populates="project", lazy="noload")
    user_projects: Mapped[list["UserProject"]] = relationship(
        "UserProject", back_populates="project", lazy="noload", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        schemas_count = len(self.schemas) if self.schemas else "?"
        datasets_count = len(self.datasets) if self.datasets else "?"
        users_count = len(self.user_projects) if self.user_projects else "?"
        return (
            f"<Project id={self.id} name={self.name!r} "
            f"status={self.status!r} org_id={self.organisation_id} "
            f"schemas={schemas_count} datasets={datasets_count} users={users_count}>"
        )
