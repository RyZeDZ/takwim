"""Compare the CP-SAT solver (ai/solver.py) with the backend's built-in greedy solver.

Runs on a temporary copy of the synthetic demo department, so it never touches real data:

    cd backend && .venv/bin/python ../ai/benchmark.py

Measures, for each solver: time, sessions placed, clashes (re-checked by the backend), gaps
per group per week, professors' "rather not" slots used, sessions over the "in a row" limit,
one-class days, TD / TP before their lecture, and the sessions moved after the
busiest classroom closes for repairs (the room is closed, then the timetable is re-solved).
"""
import os
import resource
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/bench.db"
os.environ.setdefault("SOLVER_TIME_LIMIT", "10")
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from sqlalchemy import select  # noqa: E402

from ai import solver as cpsat  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.demo_data import seed_demo  # noqa: E402
from app.models import Room  # noqa: E402
from app.services import fallback_solver  # noqa: E402
from app.services.groups import build_groups  # noqa: E402
from app.services.solver_adapter import build_input, find_conflicts, gaps_per_group  # noqa: E402


def moved(before, after):
    old = {a["requirement_id"]: a for a in before}
    return sum(1 for a in after if a["requirement_id"] in old and any(
        old[a["requirement_id"]][k] != a[k] for k in ("prof_id", "room_id", "day", "slot")))


def avoided(data, assignments):
    avoid = {(p["id"], d, s) for p in data["professors"] for d, s in p.get("avoid", [])}
    return sum(1 for a in assignments if (a["prof_id"], a["day"], a["slot"]) in avoid)


def student_days(data, assignments):
    """Per group and day, the occupied slots (own sessions + the section's lectures)."""
    reqs = {r["id"]: r for r in data["requirements"]}
    parent = {g["id"]: g.get("parent_id") for g in data["groups"]}
    leaves = set(parent) - set(parent.values())
    days = defaultdict(set)
    for a in assignments:
        for leaf in leaves:
            g = leaf
            while g is not None:
                if g == reqs[a["requirement_id"]]["group_id"]:
                    days[leaf, a["day"]].add(a["slot"])
                g = parent[g]
    return days


def comfort(data, assignments):
    """Student comfort: long runs, one-class days, TD/TP before its lecture on the same day."""
    limit = data.get("options", {}).get("max_in_a_row", 3)
    over = single = holes = 0
    groups = len({g for g, _ in student_days(data, assignments)}) or 1
    for slots in student_days(data, assignments).values():
        taken = [s in slots for s in range(len(data["slots"]))]
        run = 0
        for s, busy in enumerate(taken):
            run = run + 1 if busy else 0
            over += run > limit
        # an empty stretch between classes is a break when the classes on both sides add up
        # to more than the limit; otherwise it is a hole
        s = 0
        while s < len(taken):
            if taken[s]:
                s += 1
                continue
            end = s
            while end < len(taken) and not taken[end]:
                end += 1
            if 0 < s and end < len(taken):
                before = after = 0
                while s - before - 1 >= 0 and taken[s - before - 1]:
                    before += 1
                while end + after < len(taken) and taken[end + after]:
                    after += 1
                holes += (end - s) - (1 if before + after > limit else 0)
            s = end
        single += len(slots) == 1
    reqs = {r["id"]: r for r in data["requirements"]}
    lecture_at = {(reqs[a["requirement_id"]]["module_id"], reqs[a["requirement_id"]]["group_id"]):
                  (a["day"], a["slot"]) for a in assignments if reqs[a["requirement_id"]]["kind"] == "lecture"}
    parent = {g["id"]: g.get("parent_id") for g in data["groups"]}
    before = 0
    for a in assignments:
        r = reqs[a["requirement_id"]]
        g = parent.get(r["group_id"])
        while r["kind"] != "lecture" and g is not None:
            lec = lecture_at.get((r["module_id"], g))
            if lec and lec[0] == a["day"] and lec[1] > a["slot"]:
                before += 1
            g = parent.get(g)
    return {"holes/group/week (gaps that are not a needed break)": round(holes / groups, 2),
            f"sessions over {limit} in a row (students)": over, "one-class days": single,
            "TD/TP before its lecture, same day": before}


def run(name, solve, data):
    t0 = time.perf_counter()
    result = solve(data)
    seconds = time.perf_counter() - t0
    a = result["assignments"]
    return a, {"solver": name, "seconds": round(seconds, 2), "placed": len(a),
               "of": len(data["requirements"]), "clashes": len(find_conflicts(data, a)),
               "gaps/group/week": gaps_per_group(data, a), "rather-not slots used": avoided(data, a),
                                 **comfort(data, a)}


def main():
    init_db()
    with SessionLocal() as db:
        seed_demo(db)
        build_groups(db)
        db.commit()
        data = build_input(db)

        rows, firsts = [], {}
        for name, solve in (("built-in greedy", fallback_solver.solve), ("CP-SAT", cpsat.solve)):
            a, row = run(name, solve, dict(data, previous=[]))
            firsts[name] = a
            rows.append(row)

        # A room closes for repairs: the busiest TD room, then re-solve from each timetable.
        rooms = {r.id: r for r in db.scalars(select(Room))}
        use = Counter(a["room_id"] for a in firsts["CP-SAT"] if rooms[a["room_id"]].type == "td")
        closed = use.most_common(1)[0][0]
        rooms[closed].active = False
        db.flush()
        data2 = build_input(db)
        for row, (name, solve) in zip(rows, (("built-in greedy", fallback_solver.solve),
                                            ("CP-SAT", cpsat.solve))):
            before = firsts[name]
            in_room = sum(1 for a in before if a["room_id"] == closed)
            a, again = run(name, solve, dict(data2, previous=before))
            row["after closing a room: clashes"] = again["clashes"]
            row["after closing a room: moved"] = f"{moved(before, a)} (had {in_room} in it)"
            row["after closing a room: seconds"] = again["seconds"]
        db.rollback()

    print(f"Demo department: {len(data['requirements'])} weekly sessions, {len(data['rooms'])} rooms, "
          f"{len(data['professors'])} professors, {len(data['groups'])} groups")
    for row in rows:
        print("-" * 60)
        for k, v in row.items():
            print(f"{k:34} {v}")
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print("-" * 60)
    print(f"peak memory of this process: {peak:.0f} MB, CPU threads for CP-SAT: "
          f"{os.getenv('SOLVER_WORKERS', '4')}")


if __name__ == "__main__":
    main()
