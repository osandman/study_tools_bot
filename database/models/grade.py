from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Date, DateTime, Text, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class Grade(Base):
    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    period: Mapped[str] = mapped_column(String(20), default="t1")
    date: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="grades")
    subject = relationship("Subject", back_populates="grades")

    __table_args__ = (
        CheckConstraint("value >= 1 AND value <= 5", name="ck_grade_value_range"),
    )

    def __repr__(self) -> str:
        return f"<Grade {self.value} subject_id={self.subject_id}>"


# Period systems
PERIOD_SYSTEMS = {
    "trimesters": {
        "name": "Триместры",
        "periods": {
            "t1": "1 триместр",
            "t2": "2 триместр",
            "t3": "3 триместр",
        },
        "month_map": {9: "t1", 10: "t1", 11: "t1", 12: "t2", 1: "t2", 2: "t2", 3: "t3", 4: "t3", 5: "t3"},
    },
    "quarters": {
        "name": "Четверти",
        "periods": {
            "q1": "1 четверть",
            "q2": "2 четверть",
            "q3": "3 четверть",
            "q4": "4 четверть",
        },
        "month_map": {9: "q1", 10: "q1", 11: "q1", 12: "q2", 1: "q2", 2: "q2", 3: "q3", 4: "q3", 5: "q3", 6: "q4"},
    },
}


def get_current_period(system: str = "trimesters") -> str:
    month = datetime.now().month
    cfg = PERIOD_SYSTEMS.get(system, PERIOD_SYSTEMS["trimesters"])
    return cfg["month_map"].get(month, list(cfg["periods"].keys())[-1])


def get_periods(system: str = "trimesters") -> dict:
    return PERIOD_SYSTEMS[system]["periods"]
