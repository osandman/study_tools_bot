from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import ForeignKey, Index, Integer, SmallInteger, String, Date, DateTime, Text, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class Grade(Base):
    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    period: Mapped[str] = mapped_column(String(20), default="t1")
    # School year by the calendar year it starts in: 2026 is 2026/27. Periods repeat every year,
    # so (school_year, period) is what identifies "1 триместр" of a particular year.
    school_year: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=lambda: current_school_year())
    date: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="grades")
    subject = relationship("Subject", back_populates="grades")

    __table_args__ = (
        CheckConstraint("value >= 1 AND value <= 5", name="ck_grade_value_range"),
        Index("ix_grades_user_year_period", "user_id", "school_year", "period"),
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
        # 1: сентябрь–октябрь, 2: ноябрь–декабрь, 3: январь–март, 4: апрель–май
        "month_map": {9: "q1", 10: "q1", 11: "q2", 12: "q2", 1: "q3", 2: "q3", 3: "q3", 4: "q4", 5: "q4", 6: "q4"},
    },
}


SCHOOL_TIMEZONE = ZoneInfo("Europe/Moscow")
SCHOOL_YEAR_START_MONTH = 9


def school_today() -> date:
    """Today where the students are. Every calendar decision goes through this one clock."""
    return datetime.now(SCHOOL_TIMEZONE).date()


def school_year_for(day: date) -> int:
    """School year starting on September 1st; summer still belongs to the year that is ending."""
    return day.year if day.month >= SCHOOL_YEAR_START_MONTH else day.year - 1


def current_school_year() -> int:
    return school_year_for(school_today())


def format_school_year(year: int) -> str:
    return f"{year}/{(year + 1) % 100:02d}"


def get_current_period(system: str = "trimesters") -> str:
    month = school_today().month
    cfg = PERIOD_SYSTEMS.get(system, PERIOD_SYSTEMS["trimesters"])
    return cfg["month_map"].get(month, list(cfg["periods"].keys())[-1])


def get_periods(system: str = "trimesters") -> dict:
    return PERIOD_SYSTEMS[system]["periods"]
