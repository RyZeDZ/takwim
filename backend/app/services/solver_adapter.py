"""The bridge between the database and the timetable solver.

An external solver can be plugged in through .env (SOLVER_MODULE=ai.solver, see app/plugins.py).
Otherwise the built-in greedy solver (fallback_solver.py) is used.

CONTRACT: solve(data) -> result, plain dicts only.

data = {
  "days":  ["Sunday", ...],                "slots": ["08:00-09:30", ...],
  "room_types_for": {"lecture": ["amphi", "td"], "td": ["td"], "tp": ["lab"]},
  "options": {"max_sessions_per_day_group": 4},
  "rooms":      [{"id", "name", "type", "capacity"}],           # open rooms only
  "groups":     [{"id", "name", "kind", "size", "parent_id"}],  # TP ⊂ TD ⊂ section
  "professors": [{"id", "name", "max_sessions", "unavailable": [[day, slot], ...]}],
  "can_teach":  [{"prof_id", "module_id", "kinds": ["lecture", "td", "tp"]}],
  "requirements": [{"id", "module_id", "module", "group_id", "kind", "size"}],
      # one entry per weekly session that must be placed
  "previous": [{"requirement_id", "prof_id", "room_id", "day", "slot"}],
      # the current timetable: keep these places when possible (fewest changes)
}

result = {
  "assignments": [{"requirement_id", "prof_id", "room_id", "day", "slot"}],
  "unscheduled": [{"requirement_id", "reason"}],
}

Every result is re-checked by `find_conflicts` against all hard rules before it is saved.
"""
import time
from collections import defaultdict
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DB

from .. import plugins
from ..models import Absence, Claim, Module, Professor, Room, Session, Teaching, Unavailability
from ..rules import get_rules
from . import fallback_solver
from .groups import GroupTree, build_groups


def get_solver():
    """(solve function, name, warning). Falls back to the built-in solver if the plug-in is broken."""
    try:
        fn, name = plugins.load("SOLVER_MODULE", "solve")
    except Exception as e:  # noqa: BLE001
        return fallback_solver.solve, "built-in", f"solver plug-in could not be loaded ({e}); used the built-in solver"
    if fn is None:
        return fallback_solver.solve, "built-in", None
    return fn, name, None


def build_input(db: DB) -> dict:
    rules = get_rules(db)
    tree = GroupTree.load(db)
    groups = list(tree.by_id.values())
    requirements = []
    n = 0

    def add(m, g, kind, count):
        nonlocal n
        for _ in range(count):
            n += 1
            requirements.append({"id": f"r{n}", "module_id": m.id, "module": m.name,
                                 "group_id": g.id, "kind": kind, "size": g.size})

    for m in db.scalars(select(Module).order_by(Module.id)):
        for g in sorted((g for g in groups if g.level_id == m.level_id), key=lambda g: g.id):
            if g.kind == "section":
                add(m, g, "lecture", m.lecture_per_week)
            elif g.kind == "td":
                add(m, g, "td", m.td_per_week)
                if not tree.children[g.id]:  # no TP subgroups: the TD group does the TP itself
                    add(m, g, "tp", m.tp_per_week)
            else:
                add(m, g, "tp", m.tp_per_week)

    unavail = defaultdict(list)
    for u in db.scalars(select(Unavailability)):
        if u.day < rules.n_days and u.slot < rules.n_slots:
            unavail[u.professor_id].append([u.day, u.slot])

    data = {
        "days": rules.day_names,
        "slots": rules.time_slots,
        "room_types_for": rules.room_types_for,
        "options": {"max_sessions_per_day_group": rules.max_sessions_per_day_per_group},
        "rooms": [{"id": r.id, "name": r.name, "type": r.type, "capacity": r.capacity}
                  for r in db.scalars(select(Room).where(Room.active.is_(True)).order_by(Room.id))],
        "groups": [{"id": g.id, "name": g.name, "kind": g.kind, "size": g.size,
                    "parent_id": g.parent_id} for g in groups],
        "professors": [{"id": p.id, "name": p.name, "max_sessions": p.max_sessions,
                        "unavailable": unavail[p.id]}
                       for p in db.scalars(select(Professor).order_by(Professor.id))],
        "can_teach": [{"prof_id": t.professor_id, "module_id": t.module_id,
                       "kinds": [k for k in t.kinds.split(",") if k]}
                      for t in db.scalars(select(Teaching))],
        "requirements": requirements,
        "previous": [],
    }
    data["previous"] = _map_current_sessions(db, data)[0]
    return data


def _map_current_sessions(db: DB, data: dict) -> tuple[list[dict], list[Session]]:
    """Match saved sessions to requirement ids. Returns (assignments, sessions not matched)."""
    pool = defaultdict(list)
    for r in data["requirements"]:
        pool[(r["module_id"], r["group_id"], r["kind"])].append(r["id"])
    out, extra = [], []
    for s in db.scalars(select(Session).order_by(Session.id)):
        ids = pool.get((s.module_id, s.group_id, s.kind))
        if ids:
            out.append({"requirement_id": ids.pop(0), "prof_id": s.professor_id,
                        "room_id": s.room_id, "day": s.day, "slot": s.slot})
        else:
            extra.append(s)
    return out, extra


class _G:
    """Tiny adapter so GroupTree works on dicts."""

    def __init__(self, g: dict):
        self.id, self.parent_id = g["id"], g.get("parent_id")


def find_conflicts(data: dict, assignments: list[dict]) -> list[str]:
    """Re-check every hard rule. Returns human-readable problems (empty list = valid)."""
    reqs = {r["id"]: r for r in data["requirements"]}
    rooms = {r["id"]: r for r in data["rooms"]}
    profs = {p["id"]: p for p in data["professors"]}
    groups = {g["id"]: g["name"] for g in data["groups"]}
    tree = GroupTree([_G(g) for g in data["groups"]])
    teach = {(t["prof_id"], t["module_id"], k) for t in data["can_teach"] for k in t["kinds"]}
    unavailable = {(p["id"], d, s) for p in data["professors"] for d, s in p["unavailable"]}
    problems = []
    prof_at, room_at, group_at = {}, {}, defaultdict(list)
    load = defaultdict(int)
    seen = set()

    def label(r):
        return f"{r['module']} ({r['kind']}, {groups.get(r['group_id'], r['group_id'])})"

    for a in assignments:
        r = reqs.get(a["requirement_id"])
        if r is None:
            problems.append(f"unknown requirement {a['requirement_id']}")
            continue
        if a["requirement_id"] in seen:
            problems.append(f"{label(r)} placed twice")
        seen.add(a["requirement_id"])
        d, s, pid, rid = a["day"], a["slot"], a["prof_id"], a["room_id"]
        if not (0 <= d < len(data["days"]) and 0 <= s < len(data["slots"])):
            problems.append(f"{label(r)}: day/slot out of range")
            continue
        if rid not in rooms:
            problems.append(f"{label(r)}: room {rid} is unknown or closed")
            continue
        room = rooms[rid]
        pname = profs.get(pid, {}).get("name", pid)
        if room["type"] not in data["room_types_for"].get(r["kind"], []):
            problems.append(f"{label(r)}: a {r['kind']} can't be in {room['name']} ({room['type']} room)")
        if room["capacity"] < r["size"]:
            problems.append(f"{label(r)}: {room['name']} too small ({room['capacity']} < {r['size']})")
        if (pid, r["module_id"], r["kind"]) not in teach:
            problems.append(f"{label(r)}: {pname} doesn't teach this")
        if (pid, d, s) in unavailable:
            problems.append(f"{label(r)}: {pname} marked this slot as unavailable")
        if (pid, d, s) in prof_at:
            problems.append(f"{label(r)}: {pname} double-booked (with {prof_at[(pid, d, s)]})")
        prof_at[(pid, d, s)] = label(r)
        if (rid, d, s) in room_at:
            problems.append(f"{label(r)}: {room['name']} double-booked (with {room_at[(rid, d, s)]})")
        room_at[(rid, d, s)] = label(r)
        group_at[(d, s)].append((r["group_id"], label(r)))
        load[pid] += 1
    for (d, s), items in group_at.items():
        for i, (g1, l1) in enumerate(items):
            rel = tree.related(g1)
            for g2, l2 in items[i + 1:]:
                if g2 in rel:
                    problems.append(f"{l1} and {l2}: same students at the same time")
    for pid, n in load.items():
        if pid in profs and n > profs[pid]["max_sessions"]:
            problems.append(f"{profs[pid]['name']} over their maximum load ({n} sessions)")
    return problems


def gaps_per_group(data: dict, assignments: list[dict]) -> float:
    """Average empty slots between a student's first and last class of the day, per week."""
    reqs = {r["id"]: r for r in data["requirements"]}
    tree = GroupTree([_G(g) for g in data["groups"]])
    by_group_day = defaultdict(set)
    for a in assignments:
        by_group_day[(reqs[a["requirement_id"]]["group_id"], a["day"])].add(a["slot"])
    leaves = tree.leaves()
    if not leaves:
        return 0.0
    total = 0
    for leaf in leaves:
        chain = [leaf, *tree.ancestors(leaf)]
        for d in range(len(data["days"])):
            occupied = set().union(*(by_group_day[(g, d)] for g in chain))
            if occupied:
                total += (max(occupied) - min(occupied) + 1) - len(occupied)
    return round(total / len(leaves), 2)


def generate(db: DB) -> dict:
    """Rebuild changed groups, solve, re-check, save. Keeps upcoming absences when possible."""
    rebuilt = [lv["level"] for lv in build_groups(db, only_changed=True)]
    data = build_input(db)
    solve, solver_name, warning = get_solver()
    t0 = time.perf_counter()
    try:
        result = solve(data)
    except Exception as e:  # noqa: BLE001  (a failing plug-in falls back to the built-in solver)
        if solver_name == "built-in":
            raise
        warning = f"solver plug-in crashed ({e}); used the built-in solver"
        solver_name = "built-in"
        result = fallback_solver.solve(data)
    seconds = round(time.perf_counter() - t0, 3)

    assignments = result.get("assignments", [])
    conflicts = find_conflicts(data, assignments)
    reqs = {r["id"]: r for r in data["requirements"]}
    group_names = {g["id"]: g["name"] for g in data["groups"]}
    previous = {p["requirement_id"]: p for p in data["previous"]}
    moved = sum(1 for a in assignments
                if a["requirement_id"] in previous and any(
                    previous[a["requirement_id"]][k] != a[k] for k in ("prof_id", "room_id", "day", "slot")))
    summary = {
        "solver": solver_name,
        "warning": warning,
        "seconds": seconds,
        "groups_rebuilt_for": rebuilt,
        "requirements": len(data["requirements"]),
        "placed": len(assignments),
        "unscheduled": [
            {**u, "module": reqs[u["requirement_id"]]["module"],
             "group": group_names[reqs[u["requirement_id"]]["group_id"]],
             "kind": reqs[u["requirement_id"]]["kind"]}
            for u in result.get("unscheduled", []) if u.get("requirement_id") in reqs],
        "conflicts": conflicts,
        "sessions_moved": moved if previous else None,
        "gaps_per_group_per_week": None if conflicts else gaps_per_group(data, assignments),
        "absences_kept": 0,
        "absences_dropped": [],
        "claims_to_review": [],
        "saved": False,
    }
    if conflicts:
        db.rollback()
        return summary  # never save an invalid timetable

    # Remember upcoming absences: the sessions they point to are about to be replaced.
    today = date.today()
    rules = get_rules(db)
    upcoming = [(a.date, a.session.module_id, a.session.group_id, a.session.kind,
                 a.session.professor_id, a.session.module.name, a.session.group.name)
                for a in db.scalars(select(Absence).where(Absence.date >= today))]

    db.execute(delete(Session))
    new_sessions = []
    for a in assignments:
        r = reqs[a["requirement_id"]]
        s = Session(module_id=r["module_id"], group_id=r["group_id"], professor_id=a["prof_id"],
                    room_id=a["room_id"], kind=r["kind"], day=a["day"], slot=a["slot"])
        db.add(s)
        new_sessions.append(s)
    db.flush()

    for when, module_id, group_id, kind, prof_id, module_name, group_name in upcoming:
        di = rules.day_index(when)
        match = next((s for s in new_sessions if (s.module_id, s.group_id, s.kind, s.professor_id, s.day)
                      == (module_id, group_id, kind, prof_id, di)), None)
        if match:
            db.add(Absence(session_id=match.id, date=when))
            summary["absences_kept"] += 1
        else:
            summary["absences_dropped"].append(
                f"{module_name} ({group_name}) on {when.isoformat()}: the session moved to another day, "
                f"the professor should check their new timetable")
    db.flush()

    # Extra sessions already booked that now collide with the new timetable.
    tree = GroupTree.load(db)
    for c in db.scalars(select(Claim).where(Claim.date >= today)):
        di = rules.day_index(c.date)
        for s in new_sessions:
            if s.day == di and s.slot == c.slot and (
                    s.room_id == c.room_id or s.professor_id == c.professor_id
                    or s.group_id in tree.related(c.group_id)):
                summary["claims_to_review"].append(
                    f"extra session of {c.professor.name} with {c.group.name} on {c.date.isoformat()} "
                    f"at {rules.slot_label(c.slot)} now overlaps the regular timetable")
                break
    db.commit()
    summary["saved"] = True
    return summary


def current_conflicts(db: DB) -> list[str]:
    """Check the saved timetable (used after a manual edit)."""
    data = build_input(db)
    assignments = list(data["previous"])
    _, extra = _map_current_sessions(db, data)
    for i, s in enumerate(extra, start=1):  # sessions no longer required: still check them
        rid = f"x{i}"
        data["requirements"].append({"id": rid, "module_id": s.module_id, "module": s.module.name,
                                     "group_id": s.group_id, "kind": s.kind, "size": s.group.size})
        assignments.append({"requirement_id": rid, "prof_id": s.professor_id, "room_id": s.room_id,
                            "day": s.day, "slot": s.slot})
    return find_conflicts(data, assignments)
