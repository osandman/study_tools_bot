import math


def grade_emoji(avg: float) -> str:
    """Return a color emoji for a grade average using school rounding."""
    rounded = math.floor(avg + 0.5)
    if rounded >= 5:
        return "🟢"
    if rounded >= 4:
        return "🟠"
    if rounded >= 3:
        return "🟡"
    if rounded >= 2:
        return "🔴"
    return "🟣"
