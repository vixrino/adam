"""Table USER_PROJECT : jointure User / Project avec rôle.

Le rôle détermine les actions autorisées au sein du projet :
  - operator   : labellise les documents
  - supervisor : supervise et valide
  - admin      : gestion complète
Clé primaire composite sur (user_id, project_id).
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.db.scoping import OrganisationScoped, org_user_ids
from adam_core.enums.roles import UserRole

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class UserProject(OrganisationScoped, Base):
    __tablename__ = "user_project"

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("project.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=UserRole.OPERATOR.value,
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

    # Relationships
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User",
        back_populates="user_projects",
        lazy="noload",
    )
    project: Mapped["Project"] = relationship(  # type: ignore[name-defined]
        "Project",
        back_populates="user_projects",
        lazy="noload",
    )

    @classmethod
    def __organisation_filter__(cls, organisation_id: int) -> "ColumnElement[bool]":
        # user_project -> user -> organisation
        return cls.user_id.in_(org_user_ids(organisation_id))

    def __repr__(self) -> str:
        return (
            f"<UserProject user_id={self.user_id} "
            f"project_id={self.project_id} role={self.role!r}>"
        )
