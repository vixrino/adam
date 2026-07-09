"""Table USER : utilisateur de la plateforme ADAM.

L'accès aux projets et les rôles associés sont gérés via USER_PROJECT.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.enums.status import UserStatus


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organisation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organisation.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    matricule: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=UserStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    organisation: Mapped["Organisation"] = relationship(  # type: ignore[name-defined]
        "Organisation",
        back_populates="users",
        lazy="noload",
    )
    user_projects: Mapped[list["UserProject"]] = relationship(  # type: ignore[name-defined]
        "UserProject",
        back_populates="user",
        lazy="noload",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list["Job"]] = relationship(  # type: ignore[name-defined]
        "Job",
        back_populates="agent",
        foreign_keys="Job.agent_id",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} status={self.status!r}>"
