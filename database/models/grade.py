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
    period: Mapped[str] = mapped_column(String(20), default="trimester_1")  # trimester_1, trimester_2, trimester_3, year
    grade_type: Mapped[str] = mapped_column(String(50), default="other")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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

PERIODS = {
    "trimester_1": "1 триместр",
    "trimester_2": "2 триместр",
    "trimester_3": "3 триместр",
    "year": "Год",
}


def get_current_period() -> str:
    """Determine current trimester based on month."""
    month = datetime.now().month
    if month in (9, 10, 11):
        return "trimester_1"
    elif month in (12, 1, 2):
        return "trimester_2"
    elif month in (3, 4, 5):
        return "trimester_3"
    else:
        return "trimester_3"  # June-August: default to last trimester
