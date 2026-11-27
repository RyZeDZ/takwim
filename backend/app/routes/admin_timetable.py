"""Admin: build groups, generate the timetable, check it, move sessions by hand."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DB

from ..auth import log, require_admin
from ..db import get_db
from ..models import Level, Professor, Room, Session
from ..rules import get_rules
from ..schemas import SessionPatch
from ..services import solver_adapter
from ..services.groups import build_groups, existing_structure
from .common import get_or_404

router = APIRouter(prefix="/admin", tags=["admin: timetable"], dependencies=[Depends(require_admin)])


# ------------------------------------------------------------------ groups & generation
@router.get("/groups")
def groups_list(db: DB = Depends(get_db)):
    """The current groups, level by level."""
    return {"levels": existing_structure(db)}


@router.post("/groups/build")
def groups_build(force: bool = False, db: DB = Depends(get_db), user=Depends(require_admin)):
    """Split headcounts into sections, TD groups and TP subgroups. Only levels whose headcount or
    group-size settings changed are rebuilt (their sessions go too); force=true rebuilds all.
    Generating the timetable does this automatically, so calling it is optional."""
    rebuilt = build_groups(db, only_changed=not force)
    log(db, user, "groups_build", f"{len(rebuilt)} levels rebuilt")
    db.commit()
    return {"rebuilt": [lv["level"] for lv in rebuilt], "levels": existing_structure(db)}


@router.post("/timetable/generate")
def generate(db: DB = Depends(get_db), user=Depends(require_admin)):
    """One button: (re)builds groups if needed, places every session, re-checks, saves.
    Re-running it keeps sessions where they are as much as possible."""
    if db.scalar(select(Level.id).limit(1)) is None:
        raise HTTPException(400, "No levels yet: import or add levels and modules first")
    result = solver_adapter.generate(db)
    log(db, user, "generate", f"{result['placed']}/{result['requirements']} placed, "
                              f"{len(result['conflicts'])} conflicts, {result['seconds']}s")
    db.commit()
    return result


@router.get("/timetable/check")
def check(db: DB = Depends(get_db)):
    """Re-check the saved timetable against every hard rule."""
    conflicts = solver_adapter.current_conflicts(db)
    return {"conflicts": conflicts, "ok": not conflicts}


@router.patch("/sessions/{session_id}")
def move_session(session_id: int, body: SessionPatch, db: DB = Depends(get_db),
                 user=Depends(require_admin)):
    """Move a session by hand. Refused (409) if it creates a clash."""
    s = get_or_404(db, Session, session_id)
    rules = get_rules(db)
    if body.day is not None and body.day >= rules.n_days:
        raise HTTPException(422, "day out of range")
    if body.slot is not None and body.slot >= rules.n_slots:
        raise HTTPException(422, "slot out of range")
    if body.room_id is not None:
        get_or_404(db, Room, body.room_id)
    if body.professor_id is not None:
        get_or_404(db, Professor, body.professor_id)
    before = set(solver_adapter.current_conflicts(db))
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    db.flush()
    db.expire_all()
    new = [c for c in solver_adapter.current_conflicts(db) if c not in before]
    if new:
        db.rollback()
        raise HTTPException(409, {"message": "This move creates a clash", "conflicts": new})
    log(db, user, "move_session", f"session {session_id} -> {body.model_dump(exclude_none=True)}")
    db.commit()
    return {"ok": True}

