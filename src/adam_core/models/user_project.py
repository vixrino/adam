"""Table USER_PROJECT : jointure User / Project avec role."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.enums.roles import UserRole


class UserProject(Base):
    __tablename__ = "user_project"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String, nullable=False, default=UserRole.OPERATOR.value)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="user_projects", lazy="noload")
    project: Mapped["Project"] = relationship("Project", back_populates="user_projects", lazy="noload")

    def __repr__(self) -> str:
        return f"<UserProject user_id={self.user_id} project_id={self.project_id} role={self.role!r}>"
