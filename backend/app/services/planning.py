from datetime import date, timedelta

from app.models.pi_cycle import PiCycle
from app.schemas.pi_cycle import SprintRead


SPRINT_DAYS = 14


def compute_sprints(cycle: PiCycle) -> list[SprintRead]:
    if not cycle.start_date:
        return []
    sprints: list[SprintRead] = []
    for index in range(cycle.sprint_count):
        start_date = cycle.start_date + timedelta(days=index * SPRINT_DAYS)
        end_date = start_date + timedelta(days=SPRINT_DAYS - 1)
        sprints.append(
            SprintRead(
                index=index,
                title=f"Спринт {index + 1}",
                start_date=start_date,
                end_date=end_date,
            )
        )
    return sprints


def workdays_between(start_date: date, end_date: date) -> int:
    days = 0
    cursor = start_date
    while cursor <= end_date:
        if cursor.weekday() < 5:
            days += 1
        cursor += timedelta(days=1)
    return days

