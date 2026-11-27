"""Create / update rooms, levels, modules and professors (used by the forms and the importer)."""
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DB

from ..auth import hash_password, new_password, unique_username
from ..models import Level, Module, Professor, Room, Teaching, Unavailability, User
from ..rules import get_rules


def professor_view(db: DB, p: Professor) -> dict:
    user = db.scalar(select(User).where(User.professor_id == p.id))
    teaches = [{"module_id": t.module_id, "kinds": [k for k in t.kinds.split(",") if k]}
               for t in db.scalars(select(Teaching).where(Teaching.professor_id == p.id))]
    filled = db.scalar(select(func.count()).select_from(Unavailability)
                       .where(Unavailability.professor_id == p.id)) > 0
    return {"id": p.id, "name": p.name, "max_sessions": p.max_sessions,
            "username": user.username if user else None, "teaches": teaches,
            "availability_filled": filled}


def create_professor(db: DB, name: str, max_sessions: int | None = None) -> tuple[Professor, str, str]:
    """Create a professor and their login. Returns (professor, username, one-time password)."""
    if max_sessions is None:
        max_sessions = get_rules(db).default_max_sessions_per_professor
    p = Professor(name=name.strip(), max_sessions=max_sessions)
    db.add(p)
    db.flush()
    username, password = unique_username(db, p.name), new_password()
    db.add(User(username=username, password_hash=hash_password(password), role="prof",
                professor_id=p.id))
    db.flush()
    return p, username, password


def set_teaching(db: DB, prof_id: int, module_id: int, kinds: list[str]) -> None:
    t = db.scalar(select(Teaching).where(Teaching.professor_id == prof_id,
                                         Teaching.module_id == module_id))
    value = ",".join(dict.fromkeys(kinds)) or "lecture,td,tp"
    if t:
        t.kinds = value
    else:
        db.add(Teaching(professor_id=prof_id, module_id=module_id, kinds=value))


def commit_rows(db: DB, kind: str, rows: list[dict]) -> dict:
    created, updated, skipped, credentials, warnings = 0, 0, 0, [], []
    for n, row in enumerate(rows, start=1):
        name = str(row.get("name", "")).strip()
        if not name:
            skipped += 1
            continue
        if kind == "rooms":
            cap = row.get("capacity")
            if not cap:
                warnings.append(f"row {n}: room '{name}' has no capacity, skipped")
                skipped += 1
                continue
            r = db.scalar(select(Room).where(Room.name == name))
            rtype = row.get("type") if row.get("type") in ("amphi", "td", "lab") else "td"
            if r:
                r.type, r.capacity = rtype, int(cap)
                updated += 1
            else:
                db.add(Room(name=name, type=rtype, capacity=int(cap)))
                created += 1
        elif kind == "levels":
            hc = row.get("headcount")
            if not hc:
                warnings.append(f"row {n}: level '{name}' has no headcount, skipped")
                skipped += 1
                continue
            lv = db.scalar(select(Level).where(Level.name == name))
            if lv:
                lv.headcount = int(hc)
                updated += 1
            else:
                db.add(Level(name=name, headcount=int(hc)))
                created += 1
        elif kind == "modules":
            level = db.scalar(select(Level).where(func.lower(Level.name) ==
                                                   str(row.get("level", "")).strip().lower()))
            if not level:
                warnings.append(f"row {n}: level '{row.get('level')}' not found "
                                f"(import levels first), module '{name}' skipped")
                skipped += 1
                continue
            m = db.scalar(select(Module).where(Module.level_id == level.id, Module.name == name))
            values = dict(lecture_per_week=int(row.get("lecture") or 0),
                          td_per_week=int(row.get("td") or 0), tp_per_week=int(row.get("tp") or 0))
            if m:
                for k, v in values.items():
                    setattr(m, k, v)
                updated += 1
            else:
                db.add(Module(level_id=level.id, name=name, **values))
                created += 1
        elif kind == "professors":
            p = db.scalar(select(Professor).where(Professor.name == name))
            if p:
                p.max_sessions = int(row.get("max_sessions") or p.max_sessions)
                updated += 1
            else:
                max_s = int(row["max_sessions"]) if row.get("max_sessions") else None
                p, username, password = create_professor(db, name, max_s)
                credentials.append({"name": name, "username": username, "password": password})
                created += 1
            kinds = [k for k in str(row.get("kinds") or "lecture,td,tp").split(",") if k]
            for mod_name in row.get("modules") or []:
                mods = list(db.scalars(select(Module).where(
                    func.lower(Module.name) == mod_name.strip().lower())))
                if not mods:
                    warnings.append(f"row {n}: module '{mod_name}' not found for {name} "
                                    f"(import modules first)")
                for m in mods:
                    set_teaching(db, p.id, m.id, kinds)
        db.flush()
    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped,
            "warnings": warnings, "credentials": credentials}


def save_availability(db: DB, prof_id: int, body) -> dict:
    """Replace a professor's grid of 'I can't' slots."""
    rules = get_rules(db)
    for ref in body.unavailable:
        if ref.day >= rules.n_days or ref.slot >= rules.n_slots:
            raise HTTPException(422, f"day/slot out of range: {ref.day}/{ref.slot}")
    db.execute(delete(Unavailability).where(Unavailability.professor_id == prof_id))
    unique = {(r.day, r.slot) for r in body.unavailable}
    for d, s in sorted(unique):
        db.add(Unavailability(professor_id=prof_id, day=d, slot=s))
    db.commit()
    return {"unavailable": [{"day": d, "slot": s} for d, s in sorted(unique)]}
