from datetime import datetime, date

from sqlalchemy import ForeignKey, Integer, String, Date, DateTime, Text, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class Grade(Base):
    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    grade_type: Mapped[str] = mapped_column(String(50), default="other")  # homework, test, exam, classwork, other
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # описание/тема
    date: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="grades")
    subject = relationship("Subject", back_populates="grades")

    __table_args__ = (
        CheckConstraint("value >= 1 AND value <= 5", name="ck_grade_value_range"),
    )

    def __repr__(self) -> str:
        return f"<Grade {self.value} ({self.grade_type}) subject_id={self.subject_id}>"


GRADE_TYPES = {
    "homework": "📝 Домашняя работа",
    "test": "📋 Контрольная",
    "exam": "🎓 Экзамен",
    "classwork": "✏️ Классная работа",
    "other": "📌 Другое",
}
