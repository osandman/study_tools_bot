import math


def calculate_needed_grades(counts: dict[int, int]) -> tuple[int, int]:
    """Calculate how many 5s needed for average 4.5 and 3.5.
    Returns: (fives_for_5, fives_for_4). If target is already reached or impossible, returns 0.
    """
    total_grades = sum(counts.values())
    if total_grades == 0:
        return 0, 0

    current_sum = sum(val * count for val, count in counts.items())
    
    def get_needed(target_avg: float) -> int:
        # formula: (current_sum + 5*x) / (total_grades + x) = target_avg
        # current_sum + 5x = target_avg * total_grades + target_avg * x
        # x * (5 - target_avg) = target_avg * total_grades - current_sum
        # x = (target_avg * total_grades - current_sum) / (5 - target_avg)
        if 5 <= target_avg:
            return 0
        current_avg = current_sum / total_grades
        if current_avg >= target_avg:
            return 0
        
        needed = (target_avg * total_grades - current_sum) / (5 - target_avg)
        import math
        return max(0, math.ceil(needed))

    return get_needed(4.5), get_needed(3.5)

def grade_emoji(avg: float) -> str:
    """Return a color emoji for a grade average using school rounding."""
    rounded = math.floor(float(avg) + 0.5)
    if rounded >= 5:
        return "🟢"
    if rounded >= 4:
        return "🟡"
    if rounded >= 3:
        return "🟠"
    if rounded >= 2:
        return "🔴"
    return "🟣"
