from datetime import date, datetime, timezone

import database.models.grade as grade_module
from database.models.grade import format_school_year, school_year_for


def test_school_year_starts_on_september_first():
    assert school_year_for(date(2026, 8, 31)) == 2025  # summer closes the year that is ending
    assert school_year_for(date(2026, 9, 1)) == 2026
    assert school_year_for(date(2027, 5, 31)) == 2026


def test_school_year_label():
    assert format_school_year(2026) == "2026/27"
    assert format_school_year(2099) == "2099/00"


def test_school_today_uses_moscow_time(monkeypatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            moment = datetime(2026, 8, 31, 22, 30, tzinfo=timezone.utc)  # 01:30 September 1st in Moscow
            return moment.astimezone(tz) if tz else moment

    monkeypatch.setattr(grade_module, "datetime", FrozenDatetime)

    assert grade_module.school_today() == date(2026, 9, 1)
    assert grade_module.current_school_year() == 2026
