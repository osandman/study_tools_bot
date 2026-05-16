from datetime import datetime

from sqlalchemy import BigInteger, String, Boolean, DateTime, ForeignKey, Integer, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)  # предустановленный предмет
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="subjects")
    grades = relationship("Grade", back_populates="subject", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_subject"),
    )

    def __repr__(self) -> str:
        return f"<Subject {self.name} (user_id={self.user_id})>"


DEFAULT_SUBJECTS = [
    "Алгебра",
    "Геометрия",
    "Русский язык",
    "Литература",
    "Физика",
    "Химия",
    "Биология",
    "История",
    "Обществознание",
    "География",
    "Английский язык",
    "Информатика",
    "Физкультура",
]
