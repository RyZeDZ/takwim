"""Professor space: own timetable, availability grid, absences, extra sessions."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DB

from ..auth import current_user, log, require_prof
from ..db import get_db
from ..models import Absence, Claim, Group, Module, Room, Session, Unavailability, User
from ..rules import KIND_FOR_GROUP, get_rules
from ..schemas import AbsenceIn, AvailabilityIn, ClaimIn, SlotSearchIn
from ..services.catalog import save_availability
from ..services.groups import GroupTree
from ..services.live import find_slots, occupancy, slot_problems, teaches_group, week_view

router = APIRouter(prefix="/me", tags=["professor"])


# ------------------------------------------------------------------ timetable
@router.get("/timetable")
def my_timetable(user: User = Depends(require_prof), db: DB = Depends(get_db)):
    """The logged-in professor's weekly (recurring) sessions."""
    rows = db.scalars(select(Session).where(Session.professor_id == user.professor_id)
                      .order_by(Session.day, Session.slot))
    return [{"session_id": s.id, "day": s.day, "slot": s.slot, "module": s.module.name,
             "module_id": s.module_id, "kind": s.kind, "group": s.group.name,
             "group_id": s.group_id, "room": s.room.name} for s in rows]


@router.get("/week")
def my_week(day: date | None = Query(None, alias="date"), user: User = Depends(require_prof),
            db: DB = Depends(get_db)):
    """The professor's live week, with cancelled and extra sessions. ?date=YYYY-MM-DD (any day of the week)"""
    return week_view(db, prof_id=user.professor_id, any_date=day or date.today())


@router.get("/groups")
def my_groups(user: User = Depends(require_prof), db: DB = Depends(get_db)):
    """Groups and modules the professor teaches (for the extra-session form)."""
    rows = db.scalars(select(Session).where(Session.professor_id == user.professor_id))
    seen = {}
    for s in rows:
        key = (s.group_id, s.module_id)
        seen[key] = {"group_id": s.group_id, "group": s.group.name, "group_kind": s.group.kind,
                     "size": s.group.size, "module_id": s.module_id, "module": s.module.name,
                     "kind": s.kind}
    return sorted(seen.values(), key=lambda x: (x["group"], x["module"]))


# ------------------------------------------------------------------ availability grid
@router.get("/availability", response_model=AvailabilityIn)
def get_availability(user: User = Depends(require_prof), db: DB = Depends(get_db)):
    rows = db.scalars(select(Unavailability).where(Unavailability.professor_id == user.professor_id))
    return {"unavailable": [{"day": u.day, "slot": u.slot} for u in rows]}


@router.put("/availability", response_model=AvailabilityIn)
def put_availability(body: AvailabilityIn, user: User = Depends(require_prof),
                     db: DB = Depends(get_db)):
    """Replace the professor's grid: the (day, slot) pairs they can't teach. Used at the next generation."""
    result = save_availability(db, user.professor_id, body)
    log(db, user, "availability", f"{len(result['unavailable'])} slots")
    db.commit()
    return result


# ------------------------------------------------------------------ absences
@router.post("/absences", status_code=201)
def declare_absence(body: AbsenceIn, user: User = Depends(current_user),
                    db: DB = Depends(get_db)):
    """Cancel one occurrence of a weekly session. Frees the room for that date.
    Safe to repeat (offline replays): declaring the same absence twice returns the first one."""
    s = db.get(Session, body.session_id)
    if s is None:
        raise HTTPException(404, "Session not found")
    if user.role == "prof" and s.professor_id != user.professor_id:
        raise HTTPException(403, "This is not your session")
    if body.date < date.today():
        raise HTTPException(422, "This date is in the past")
    rules = get_rules(db)
    if rules.day_index(body.date) != s.day:
        raise HTTPException(422, f"This session is on {rules.day_label(s.day)}, "
                                 f"not on {body.date.isoformat()}")
    existing = db.scalar(select(Absence).where(Absence.session_id == s.id,
                                               Absence.date == body.date))
    if existing:
        return _absence_out(existing)
    a = Absence(session_id=s.id, date=body.date)
    db.add(a)
    log(db, user, "absence", f"{s.module.name} {s.group.name} {body.date} slot {s.slot} "
                             f"-> room {s.room.name} freed")
    db.commit()
    return _absence_out(a)


def _absence_out(a: Absence) -> dict:
    s = a.session
    return {"id": a.id, "session_id": s.id, "date": a.date.isoformat(), "slot": s.slot,
            "module": s.module.name, "group": s.group.name, "room_freed": s.room.name}


@router.get("/absences")
def my_absences(user: User = Depends(require_prof), db: DB = Depends(get_db)):
    rows = db.scalars(select(Absence).join(Session)
                      .where(Session.professor_id == user.professor_id,
                             Absence.date >= date.today()).order_by(Absence.date))
    return [_absence_out(a) for a in rows]


@router.delete("/absences/{absence_id}")
def undo_absence(absence_id: int, user: User = Depends(current_user), db: DB = Depends(get_db)):
    """Cancel an absence. Refused if the freed slot has already been booked."""
    a = db.get(Absence, absence_id)
    if a is None:
        raise HTTPException(404, "Absence not found")
    s = a.session
    if user.role == "prof" and s.professor_id != user.professor_id:
        raise HTTPException(403, "This is not your absence")
    tree = GroupTree.load(db)
    blocking = db.scalars(select(Claim).where(
        Claim.date == a.date, Claim.slot == s.slot,
        or_(Claim.room_id == s.room_id, Claim.group_id.in_(tree.related(s.group_id)),
            Claim.professor_id == s.professor_id))).first()
    if blocking:
        raise HTTPException(409, f"Too late: {blocking.professor.name} already booked "
                                 f"{blocking.room.name} / {blocking.group.name} at that time")
    db.delete(a)
    log(db, user, "absence_undo", f"session {s.id} {a.date}")
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ extra sessions
@router.post("/slots/search")
def search_slots(body: SlotSearchIn, user: User = Depends(require_prof),
                 db: DB = Depends(get_db)):
    """Ranked (date, time, room) options where the professor, the group and a room are all free."""
    if db.get(Group, body.group_id) is None:
        raise HTTPException(404, "Group not found")
    if not teaches_group(db, GroupTree.load(db), user.professor_id, body.group_id):
        raise HTTPException(403, "You don't teach this group")
    rules = get_rules(db)
    today = date.today()
    if body.date_from is None:
        d_from, d_to = rules.default_search_range(today)
        d_to = body.date_to or d_to
    else:
        d_from = body.date_from
        d_to = body.date_to or rules.default_search_range(d_from)[1]
    if d_to < d_from:
        raise HTTPException(422, "date_to is before date_from")
    if (d_to - d_from).days > 31:
        raise HTTPException(422, "Search at most one month at a time")
    options = find_slots(db, user.professor_id, body.group_id, d_from, d_to,
                         kind=body.kind, limit=body.limit, today=today)
    return {"from": d_from.isoformat(), "to": d_to.isoformat(), "options": options}


@router.post("/claims", status_code=201)
def claim(body: ClaimIn, user: User = Depends(require_prof), db: DB = Depends(get_db)):
    """Book a slot for an extra session. First claim wins: a slot taken in the meantime -> 409 + alternatives."""
    group = db.get(Group, body.group_id)
    room = db.get(Room, body.room_id)
    if group is None or room is None:
        raise HTTPException(404, "Group or room not found")
    if body.module_id is not None and db.get(Module, body.module_id) is None:
        raise HTTPException(404, "Module not found")
    if body.date < date.today():
        raise HTTPException(422, "This date is in the past")
    rules = get_rules(db)
    if not rules.is_working_day(body.date):
        raise HTTPException(422, "Not a working day")

    # Offline replay: the same claim sent twice returns the first one.
    same = db.scalar(select(Claim).where(Claim.professor_id == user.professor_id,
                                         Claim.room_id == room.id, Claim.date == body.date,
                                         Claim.slot == body.slot, Claim.group_id == group.id))
    if same:
        return _claim_out(same, rules)

    tree = GroupTree.load(db)
    if not teaches_group(db, tree, user.professor_id, group.id):
        raise HTTPException(403, "You don't teach this group")
    kind = body.kind or KIND_FOR_GROUP[group.kind]
    problems = slot_problems(db, rules, occupancy(db, body.date, rules), tree, user.professor_id,
                             group, room, body.slot, kind)
    if problems:
        raise HTTPException(409, {"message": "This slot is no longer available",
                                  "problems": problems,
                                  "alternatives": _alternatives(db, user, group.id, body, kind)})
    c = Claim(professor_id=user.professor_id, group_id=group.id, module_id=body.module_id,
              room_id=room.id, date=body.date, slot=body.slot)
    db.add(c)
    try:
        db.commit()
    except IntegrityError:  # two claims at the very same moment: the database decides
        db.rollback()
        raise HTTPException(409, {"message": "Someone just booked this room",
                                  "problems": ["room taken a moment ago"],
                                  "alternatives": _alternatives(db, user, group.id, body, kind)})
    log(db, user, "claim", f"{group.name} {room.name} {body.date} slot {body.slot}")
    db.commit()
    return _claim_out(c, rules)


def _alternatives(db: DB, user: User, group_id: int, body: ClaimIn, kind: str) -> list[dict]:
    d_from, d_to = get_rules(db).default_search_range(body.date)
    return find_slots(db, user.professor_id, group_id, max(body.date, d_from), d_to,
                      kind=kind, limit=3)


def _claim_out(c: Claim, rules) -> dict:
    return {"id": c.id, "date": c.date.isoformat(), "slot": c.slot,
            "time": rules.slot_label(c.slot), "group": c.group.name, "room": c.room.name,
            "module": c.module.name if c.module else None, "professor": c.professor.name}


@router.get("/claims")
def my_claims(user: User = Depends(require_prof), db: DB = Depends(get_db)):
    rows = db.scalars(select(Claim).where(Claim.professor_id == user.professor_id,
                                          Claim.date >= date.today()).order_by(Claim.date, Claim.slot))
    rules = get_rules(db)
    return [_claim_out(c, rules) for c in rows]


@router.delete("/claims/{claim_id}")
def cancel_claim(claim_id: int, user: User = Depends(require_prof), db: DB = Depends(get_db)):
    c = db.get(Claim, claim_id)
    if c is None:
        raise HTTPException(404, "Claim not found")
    if c.professor_id != user.professor_id:
        raise HTTPException(403, "This is not your claim")
    db.delete(c)
    log(db, user, "claim_cancel", f"claim {claim_id}")
    db.commit()
    return {"ok": True}
