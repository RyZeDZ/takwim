"""The department's rules: working days, time slots, group sizes, room types...

They are stored in the database (table app_settings) and the admin edits them from the app
(GET/PUT /admin/settings).
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DB

from .models import AppSetting

WEEKDAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
ROOM_TYPES = ["amphi", "td", "lab"]
SESSION_KINDS = ["lecture", "td", "tp"]

# Which session kind belongs to which group kind (structural, not a rule).
KIND_FOR_GROUP = {"section": "lecture", "td": "td", "tp": "tp"}


@dataclass
class Rules:
    week_days: list[str] = field(
        default_factory=lambda: ["sunday", "monday", "tuesday", "wednesday", "thursday"]
    )
    time_slots: list[str] = field(
        default_factory=lambda: [
            "08:00-09:30",
            "09:30-11:00",
            "11:00-12:30",
            "12:30-14:00",
            "14:00-15:30",
            "15:30-17:00",
        ]
    )
    max_sessions_per_day_per_group: int = 4
    section_max_size: int = 180
    td_group_size: int = 30
    tp_group_size: int = 15
    split_tp_groups: bool = False  # off: the TD group does the TP together
    default_max_sessions_per_professor: int = 12
    max_sessions_per_day_per_professor: int = 4
    max_sessions_in_a_row: int = 3  # soft: a break is preferred after this many back-to-back
    room_types_for: dict[str, list[str]] = field(
        default_factory=lambda: {
            "lecture": ["amphi", "td"],
            "td": ["td"],
            "tp": ["lab"],
        }
    )

    # ---------------------------------------------------------------- calendar helpers
    @property
    def day_names(self) -> list[str]:
        return [d.capitalize() for d in self.week_days]

    @property
    def n_days(self) -> int:
        return len(self.week_days)

    @property
    def n_slots(self) -> int:
        return len(self.time_slots)

    def day_index(self, d: date) -> int | None:
        """Position of this date's weekday in week_days, or None if it isn't a working day."""
        name = WEEKDAYS[d.weekday()]
        return self.week_days.index(name) if name in self.week_days else None

    def is_working_day(self, d: date) -> bool:
        return self.day_index(d) is not None

    def week_start(self, d: date) -> date:
        """The most recent date (<= d) that falls on the first working day of the week."""
        first = WEEKDAYS.index(self.week_days[0])
        return d - timedelta(days=(d.weekday() - first) % 7)

    def week_dates(self, d: date) -> list[date]:
        """The working dates of d's week, in week_days order."""
        start = self.week_start(d)
        dates = [start + timedelta(days=i) for i in range(7)]
        by_name = {WEEKDAYS[x.weekday()]: x for x in dates}
        return [by_name[name] for name in self.week_days]

    def default_search_range(self, today: date) -> tuple[date, date]:
        """The rest of this week; next week if this one is over."""
        dates = [x for x in self.week_dates(today) if x >= today]
        if not dates:
            dates = self.week_dates(self.week_start(today) + timedelta(days=7))
        return dates[0], dates[-1]

    def slot_label(self, slot: int) -> str:
        return self.time_slots[slot] if 0 <= slot < self.n_slots else f"slot {slot}"

    def day_label(self, day: int) -> str:
        return self.day_names[day] if 0 <= day < self.n_days else f"day {day}"

    def to_dict(self) -> dict:
        return asdict(self)


_SLOT_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d)$")


def validate(data: dict) -> list[str]:
    """Return the problems with a rules dict (empty list = valid)."""
    errors = []
    days = data["week_days"]
    if not days or len(set(days)) != len(days) or any(d not in WEEKDAYS for d in days):
        errors.append(f"week_days: 1 to 7 different names among {WEEKDAYS}")
    else:
        first = WEEKDAYS.index(days[0])
        offsets = [(WEEKDAYS.index(d) - first) % 7 for d in days]
        if offsets != sorted(offsets):
            errors.append(
                "week_days must be in calendar order, starting with the first day of the week"
            )
    prev_end = -1
    for s in data["time_slots"]:
        m = _SLOT_RE.match(s or "")
        if not m:
            errors.append(f"time slot '{s}' must look like 08:00-09:30")
            continue
        start = int(m[1]) * 60 + int(m[2])
        end = int(m[3]) * 60 + int(m[4])
        if end <= start:
            errors.append(f"time slot '{s}' ends before it starts")
        if start < prev_end:
            errors.append(
                f"time slot '{s}' overlaps the previous one (keep them in order)"
            )
        prev_end = end
    if not data["time_slots"]:
        errors.append("at least one time slot is needed")
    for key in (
        "max_sessions_per_day_per_group",
        "section_max_size",
        "td_group_size",
        "tp_group_size",
        "default_max_sessions_per_professor",
        "max_sessions_per_day_per_professor",
        "max_sessions_in_a_row",
    ):
        if not isinstance(data[key], int) or data[key] < 1:
            errors.append(f"{key} must be a whole number >= 1")
    rt = data["room_types_for"]
    if set(rt) != set(SESSION_KINDS):
        errors.append(f"room_types_for needs exactly the keys {SESSION_KINDS}")
    else:
        for kind, types in rt.items():
            if not types or any(t not in ROOM_TYPES for t in types):
                errors.append(f"room_types_for.{kind}: one or more of {ROOM_TYPES}")
    return errors


def get_rules(db: DB) -> Rules:
    rules = Rules()
    row = db.scalar(select(AppSetting).where(AppSetting.key == "rules"))
    if row:
        stored = json.loads(row.value)
        for k, v in stored.items():
            if hasattr(rules, k):
                setattr(rules, k, v)
    return rules


def save_rules(db: DB, rules: Rules) -> None:
    row = db.scalar(select(AppSetting).where(AppSetting.key == "rules"))
    value = json.dumps(rules.to_dict())
    if row:
        row.value = value
    else:
        db.add(AppSetting(key="rules", value=value))
    db.flush()
