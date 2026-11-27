"""Admin: the department's rules (days, time slots, group sizes...), editable at any time."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DB

from ..auth import log, require_admin
from ..db import get_db
from ..models import Session, Unavailability
from ..rules import Rules, get_rules, save_rules, validate
from ..services import solver_adapter

router = APIRouter(prefix="/admin", tags=["admin: settings"], dependencies=[Depends(require_admin)])

# Changing one of these makes the current timetable invalid, so it is regenerated right away.
RESHAPING = {"week_days", "time_slots", "section_max_size", "td_group_size", "tp_group_size",
             "split_tp_groups", "room_types_for"}


@router.get("/settings")
def get_settings(db: DB = Depends(get_db)):
    return {"rules": get_rules(db).to_dict(), "defaults": Rules().to_dict()}


@router.put("/settings")
def update_settings(changes: dict, db: DB = Depends(get_db), user=Depends(require_admin)):
    """Send only what changes, e.g. {"time_slots": ["08:00-09:30", ...]} or {"td_group_size": 25}.
    If the change reshapes the week or the groups, the timetable is regenerated immediately."""
    current = get_rules(db)
    data = current.to_dict()
    unknown = [k for k in changes if k not in data]
    if unknown:
        raise HTTPException(422, f"Unknown setting(s): {unknown}. Known: {list(data)}")
    if "week_days" in changes and isinstance(changes["week_days"], list):
        changes["week_days"] = [str(d).strip().lower() for d in changes["week_days"]]
    data.update(changes)
    errors = validate(data)
    if not isinstance(data.get("split_tp_groups"), bool):
        errors.append("split_tp_groups must be true or false")
    if errors:
        raise HTTPException(422, {"message": "Invalid settings", "errors": errors})
    changed = sorted(k for k in changes if changes[k] != current.to_dict()[k])
    new_rules = Rules(**data)
    save_rules(db, new_rules)
    notes = []
    if {"week_days", "time_slots"} & set(changed):
        removed = db.execute(delete(Unavailability).where(
            (Unavailability.day >= new_rules.n_days) | (Unavailability.slot >= new_rules.n_slots)))
        notes.append("The week changed: professors should check their availability grid"
                     + (f" ({removed.rowcount} slots no longer exist and were removed)."
                        if removed.rowcount else "."))
    log(db, user, "settings", ", ".join(changed) or "no change")
    db.commit()

    regenerated = None
    if RESHAPING & set(changed) and db.scalar(select(Session.id).limit(1)) is not None:
        regenerated = solver_adapter.generate(db)
        if not regenerated["saved"]:
            notes.append("The current timetable does not fit the new settings and could not be "
                         "regenerated automatically: see 'conflicts' and 'unscheduled'.")
    return {"rules": new_rules.to_dict(), "changed": changed, "regenerated": regenerated,
            "notes": notes}
