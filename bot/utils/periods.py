from database.models import User
from database.models.grade import current_school_year, get_current_period


def get_active_period(user: User) -> str:
    """Period of the current school year the user works with: the one pinned in /settings this
    school year, otherwise the current one by the school calendar."""
    if user.active_period and user.active_school_year == current_school_year():
        return user.active_period
    return get_current_period(user.period_system)
