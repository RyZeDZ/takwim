"""Student-facing endpoints. No login, no personal data."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as DB

from ..db import get_db
from ..models import Group, Level, Room
from ..rules import get_rules
from ..services.groups import GroupTree
from ..services.live import occupancy, week_view

router = APIRouter(prefix="/public", tags=["public (students)"])


@router.get("/config")
def config(db: DB = Depends(get_db)):
    """Days and time slots, so the frontend draws the grid the same way as the backend."""
    rules = get_rules(db)
    today = date.today()
    return {"days": rules.day_names, "slots": rules.time_slots, "today": today.isoformat(),
            "week_start": rules.week_start(today).isoformat(),
            "today_is_working_day": rules.is_working_day(today)}


@router.get("/groups")
def groups(db: DB = Depends(get_db)):
    """Level -> section -> TD group -> TP subgroups, for the 'pick your group' screen."""
    tree = GroupTree.load(db)
    levels = {lv.id: lv.name for lv in db.scalars(select(Level))}

    def node(gid):
        g = tree.by_id[gid]
        return {"id": g.id, "name": g.name, "kind": g.kind, "size": g.size,
                "children": [node(c) for c in sorted(tree.children[gid])]}

    out = {}
    for g in sorted(tree.by_id.values(), key=lambda g: g.name):
        if g.parent_id is None:
            out.setdefault(levels.get(g.level_id, "?"), []).append(node(g.id))
    return [{"level": k, "sections": v} for k, v in sorted(out.items())]


@router.get("/groups/{group_id}/week")
def group_week(group_id: int, day: date | None = Query(None, alias="date"),
               db: DB = Depends(get_db)):
    """The live week of a group: sessions with status normal / cancelled, plus new extra sessions."""
    if db.get(Group, group_id) is None:
        raise HTTPException(404, "Group not found")
    return week_view(db, group_id=group_id, any_date=day or date.today())


@router.get("/free-rooms")
def free_rooms(day: date = Query(..., alias="date"), slot: int = Query(..., ge=0),
               db: DB = Depends(get_db)):
    """Rooms that are free on a given date and slot."""
    rules = get_rules(db)
    if slot >= rules.n_slots:
        raise HTTPException(422, "slot out of range")
    occ = occupancy(db, day, rules)
    rooms = db.scalars(select(Room).where(Room.active.is_(True)).order_by(Room.name))
    return [{"id": r.id, "name": r.name, "type": r.type, "capacity": r.capacity,
             "freed_by_absence": (r.id, slot) in occ.freed_rooms}
            for r in rooms if (r.id, slot) not in occ.room]
