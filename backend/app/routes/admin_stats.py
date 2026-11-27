"""Admin: dashboard numbers, action log, demo data."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DB

from ..auth import log, require_admin
from ..config import settings
from ..rules import get_rules
from ..db import get_db
from ..models import Absence, ActionLog, Claim, Level, Module, Professor, Room, Session, Unavailability

router = APIRouter(prefix="/admin", tags=["admin: dashboard"], dependencies=[Depends(require_admin)])


# ------------------------------------------------------------------ stats & logs
@router.get("/stats")
def stats(db: DB = Depends(get_db)):
    count = lambda m: db.scalar(select(func.count()).select_from(m))  # noqa: E731
    n_rooms = db.scalar(select(func.count()).select_from(Room).where(Room.active.is_(True)))
    rules = get_rules(db)
    weekly_capacity = n_rooms * rules.n_days * rules.n_slots
    n_sessions = count(Session)
    absences = list(db.scalars(select(Absence)))
    claims = list(db.scalars(select(Claim)))
    freed = {(a.session.room_id, a.date, a.session.slot) for a in absences}
    reused = sum(1 for c in claims if (c.room_id, c.date, c.slot) in freed)
    profs_filled = db.scalar(select(func.count(func.distinct(Unavailability.professor_id))))
    return {
        "rooms_active": n_rooms, "levels": count(Level), "modules": count(Module),
        "professors": count(Professor), "professors_with_availability": profs_filled,
        "sessions_per_week": n_sessions,
        "room_occupancy_percent": round(100 * n_sessions / weekly_capacity, 1) if weekly_capacity else 0,
        "absences": len(absences), "upcoming_absences": sum(1 for a in absences if a.date >= date.today()),
        "extra_sessions": len(claims), "freed_rooms_reused": reused,
    }


@router.get("/logs")
def logs(limit: int = 100, db: DB = Depends(get_db)):
    rows = db.scalars(select(ActionLog).order_by(ActionLog.id.desc()).limit(limit))
    return [{"at": r.at.isoformat(timespec="seconds"), "user": r.username, "action": r.action,
             "detail": r.detail} for r in rows]


# ------------------------------------------------------------------ demo data
@router.post("/demo/seed")
def demo_seed(db: DB = Depends(get_db), user=Depends(require_admin)):
    """Load the synthetic demo department. Only when DEMO_MODE=1 in .env, and only into an
    empty database: it can never erase a department's real data."""
    from ..demo_data import is_empty, seed_demo

    if not settings.demo_mode:
        raise HTTPException(403, "Demo data is disabled on this server (DEMO_MODE=0)")
    if not is_empty(db):
        raise HTTPException(409, "The database already has data: demo data only goes into an empty one")
    info = seed_demo(db)
    log(db, user, "demo_seed", f"{info['professors']} professors")
    db.commit()
    return info
