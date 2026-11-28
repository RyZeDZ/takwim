"""Live mode: who/what is busy on a given date, the slot finder, and week views.

On a precise date, a room/prof/group is busy at a slot if:
  - a weekly session sits there that day and has NOT been cancelled by an absence, or
  - a claim (extra session) was booked there on that date.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DB

from ..models import Absence, Claim, Group, Room, Session, Unavailability
from ..rules import KIND_FOR_GROUP, Rules, get_rules
from .groups import GroupTree


@dataclass
class Occupancy:
    day: date
    room: dict = field(default_factory=dict)   # (room_id, slot) -> description
    prof: dict = field(default_factory=dict)   # (prof_id, slot) -> description
    group: dict = field(default_factory=lambda: defaultdict(list))  # (group_id, slot) -> [desc]
    freed_rooms: set = field(default_factory=set)  # (room_id, slot) freed by an absence


def occupancy(db: DB, d: date, rules: Rules | None = None) -> Occupancy:
    rules = rules or get_rules(db)
    occ = Occupancy(day=d)
    di = rules.day_index(d)
    if di is None:
        return occ
    cancelled = {a.session_id for a in db.scalars(select(Absence).where(Absence.date == d))}
    for s in db.scalars(select(Session).where(Session.day == di)):
        label = f"{s.module.name} ({s.kind}) {s.group.name}"
        if s.id in cancelled:
            occ.freed_rooms.add((s.room_id, s.slot))
            continue
        occ.room[(s.room_id, s.slot)] = label
        occ.prof[(s.professor_id, s.slot)] = label
        occ.group[(s.group_id, s.slot)].append(label)
    for c in db.scalars(select(Claim).where(Claim.date == d)):
        label = f"extra session {c.group.name}"
        occ.room[(c.room_id, c.slot)] = label
        occ.prof[(c.professor_id, c.slot)] = label
        occ.group[(c.group_id, c.slot)].append(label)
    return occ


def slot_problems(db: DB, rules: Rules, occ: Occupancy, tree: GroupTree, prof_id: int,
                  group: Group, room: Room | None, slot: int, kind: str) -> list[str]:
    """Why this exact (date, slot, room) can't host the session. Empty list = OK."""
    problems = []
    di = rules.day_index(occ.day)
    if di is None:
        problems.append("not a working day")
        return problems
    if not 0 <= slot < rules.n_slots:
        problems.append("slot out of range")
        return problems
    if db.scalar(select(Unavailability).where(Unavailability.professor_id == prof_id,
                                              Unavailability.day == di,
                                              Unavailability.slot == slot,
                                              Unavailability.soft.is_(False))):
        problems.append("you marked this slot as unavailable")
    if (prof_id, slot) in occ.prof:
        problems.append(f"you already teach then: {occ.prof[(prof_id, slot)]}")
    for gid in tree.related(group.id):
        for what in occ.group.get((gid, slot), []):
            problems.append(f"the group is busy: {what}")
    if room is not None:
        if not room.active:
            problems.append(f"room {room.name} is closed")
        if room.type not in rules.room_types_for.get(kind, []):
            problems.append(f"room {room.name} is a {room.type} room, not suitable for {kind}")
        if room.capacity < group.size:
            problems.append(f"room {room.name} is too small ({room.capacity} < {group.size})")
        if (room.id, slot) in occ.room:
            problems.append(f"room {room.name} is taken: {occ.room[(room.id, slot)]}")
    return problems


def group_day_load(rules: Rules, occ: Occupancy, tree: GroupTree,
                   group_id: int) -> tuple[int, set[int]]:
    """How many sessions the group (and its parents/children) has that day, and at which slots."""
    slots = set()
    for gid in tree.related(group_id):
        for s in range(rules.n_slots):
            if occ.group.get((gid, s)):
                slots.add(s)
    return len(slots), slots


def find_slots(db: DB, prof_id: int, group_id: int, date_from: date, date_to: date,
               kind: str | None = None, limit: int = 10, today: date | None = None) -> list[dict]:
    """Ranked options (date, slot, room) where the professor, the group and a room are all free."""
    today = today or date.today()
    rules = get_rules(db)
    tree = GroupTree.load(db)
    group = tree.by_id.get(group_id)
    if group is None:
        return []
    kind = kind or KIND_FOR_GROUP[group.kind]
    rooms = [r for r in db.scalars(select(Room).where(Room.active.is_(True)))
             if r.type in rules.room_types_for.get(kind, []) and r.capacity >= group.size]
    options = []
    d = max(date_from, today)
    while d <= date_to:
        if rules.is_working_day(d):
            occ = occupancy(db, d, rules)
            n_today, busy_slots = group_day_load(rules, occ, tree, group_id)
            for slot in range(rules.n_slots):
                if slot_problems(db, rules, occ, tree, prof_id, group, None, slot, kind):
                    continue
                for room in rooms:
                    if (room.id, slot) in occ.room:
                        continue
                    score, reasons = 100.0, []
                    days_away = (d - date_from).days
                    score -= days_away * 4
                    if (room.id, slot) in occ.freed_rooms:
                        score += 15
                        reasons.append("reuses a room freed by an absence")
                    if n_today >= rules.max_sessions_per_day_per_group:
                        score -= 40
                        reasons.append(f"group already has {n_today} sessions that day")
                    elif n_today == 0:
                        score -= 10
                        reasons.append("group would come in just for this session")
                    if (slot - 1) in busy_slots or (slot + 1) in busy_slots:
                        score += 10
                        reasons.append("right next to another class: no gap")
                    waste = (room.capacity - group.size) / room.capacity
                    score -= waste * 20
                    if waste < 0.35:
                        reasons.append("room size fits the group")
                    options.append({
                        "date": d.isoformat(), "day": rules.day_label(rules.day_index(d)),
                        "slot": slot, "time": rules.slot_label(slot),
                        "room": {"id": room.id, "name": room.name, "type": room.type,
                                 "capacity": room.capacity},
                        "freed_by_absence": (room.id, slot) in occ.freed_rooms,
                        "score": round(score, 1), "reasons": reasons,
                    })
        d += timedelta(days=1)
    options.sort(key=lambda o: (-o["score"], o["date"], o["slot"]))
    return options[:limit]


def week_view(db: DB, *, group_id: int | None = None, prof_id: int | None = None,
              any_date: date) -> dict:
    """The live week: weekly sessions + Cancelled badges (absences) + New session badges (claims)."""
    rules = get_rules(db)
    tree = GroupTree.load(db)
    dates = rules.week_dates(any_date)
    if group_id is not None:
        # A student of this group sees its own sessions, its parents' and its subgroups'.
        gids = tree.related(group_id)
        sess_q = select(Session).where(Session.group_id.in_(gids))
        claim_q = select(Claim).where(Claim.group_id.in_(gids))
    else:
        sess_q = select(Session).where(Session.professor_id == prof_id)
        claim_q = select(Claim).where(Claim.professor_id == prof_id)
    sessions = list(db.scalars(sess_q))
    absences = {(a.session_id, a.date) for a in db.scalars(
        select(Absence).where(Absence.date >= dates[0], Absence.date <= dates[-1]))}
    entries = []
    for di, d in enumerate(dates):
        for s in sessions:
            if s.day != di:
                continue
            entries.append({
                "date": d.isoformat(), "day": di, "slot": s.slot, "time": rules.slot_label(s.slot),
                "module": s.module.name, "kind": s.kind, "group": s.group.name,
                "group_id": s.group_id, "professor": s.professor.name, "room": s.room.name,
                "session_id": s.id,
                "status": "cancelled" if (s.id, d) in absences else "normal",
            })
    for c in db.scalars(claim_q.where(Claim.date >= dates[0], Claim.date <= dates[-1])):
        entries.append({
            "date": c.date.isoformat(), "day": rules.day_index(c.date), "slot": c.slot,
            "time": rules.slot_label(c.slot), "module": c.module.name if c.module else "Extra session",
            "kind": "extra", "group": c.group.name, "group_id": c.group_id,
            "professor": c.professor.name, "room": c.room.name, "claim_id": c.id,
            "status": "new",
        })
    entries.sort(key=lambda e: (e["date"], e["slot"]))
    return {"week_start": dates[0].isoformat(), "days": rules.day_names, "slots": rules.time_slots,
            "dates": [x.isoformat() for x in dates], "entries": entries}


def teaches_group(db: DB, tree: GroupTree, prof_id: int, group_id: int) -> bool:
    """A professor may book extra sessions only for students they already teach
    (the group itself, its section, or its TD/TP subgroups)."""
    related = tree.related(group_id)
    return db.scalar(select(Session.id).where(Session.professor_id == prof_id,
                                              Session.group_id.in_(related)).limit(1)) is not None
