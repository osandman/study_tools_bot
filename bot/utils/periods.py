from database.models import User
from database.models.grade import get_current_period


def get_active_period(user: User) -> str:
    """Return active period for user, falling back to current month-based period."""
    if user.active_period:
        return user.active_period
    return get_current_period(user.period_system)
