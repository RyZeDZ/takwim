"""Timetable solver based on constraint programming (Google OR-Tools CP-SAT).

Plugged into the backend with SOLVER_MODULE=ai.solver (backend/.env). The input and output
formats are described at the top of backend/app/services/solver_adapter.py.

How it works, in short:
  * Every weekly session to place ("requirement") gets yes/no variables: which professor,
    which time (day + slot) and which kind of room. Rooms with the same type and number of
    seats are interchangeable, so the model picks a room class (e.g. "TD room, 40 seats",
    of which there are 12) and the actual room is chosen afterwards, keeping each session in
    its previous room when possible. This keeps the model small and fast.
  * Hard rules are constraints, so a solution can never break them:
      - a professor, a room and a group have at most one session at a time
        (a section's lecture blocks all of its TD / TP groups),
      - only professors who teach that module and kind, never in their "I can't" slots,
      - at most `max_sessions` per week and `max_sessions_per_day_prof` per day for a professor,
      - at most `max_sessions_per_day_group` per day for a group,
      - the right room type with enough seats,
      - every session of one module/kind/group is taught by the same professor.
  * Soft goals are penalties in the objective, which the solver makes as small as it can:
      - sessions it cannot place at all (very expensive, they are reported with a reason),
      - sessions moved compared with the current timetable (fewest changes after a re-solve),
      - empty slots between two classes in a group's day (gaps),
      - professors' "I'd rather not" slots and lower choices in their wish list,
      - the same module twice on the same day for a group, the last slot of the day.
  * The search starts from the current timetable (or from the fast built-in greedy result)
    and improves it until the time limit. The result is re-checked by the backend.

Settings (environment variables, optional):
  SOLVER_TIME_LIMIT  seconds of search (default 10)
  SOLVER_WORKERS     CPU threads used (default 4)
"""
import os
from collections import defaultdict

from ortools.sat.python import cp_model

# Penalty weights of the soft goals (higher = more important).
WEIGHTS = {
    "unscheduled": 1000,  # a session left out of the timetable
    "moved": 20,          # a session moved compared with the current timetable
    "gap": 6,             # one empty slot between two classes of a group, in one day
    "avoid": 5,           # a session in a professor's "I'd rather not" slot
    "rank": 3,            # per session, per step down the professor's wish list
    "same_day": 3,        # the same module twice on the same day for a group
    "late": 1,            # a session in the last slot of the day
    "room_type": 1,       # a second-choice room type (e.g. a lecture in a TD room)
}


def _settings():
    return (float(os.getenv("SOLVER_TIME_LIMIT", "10")),
            int(os.getenv("SOLVER_WORKERS", "4")))


def _greedy_start(data):
    """Starting point for the search: the backend's fast greedy solver, when available."""
    try:
        from app.services import fallback_solver
    except ImportError:
        return []
    try:
        return fallback_solver.solve(data)["assignments"]
    except Exception:  # noqa: BLE001  (only a hint: the search works without it)
        return []


def _greedy_full(data):
    from app.services import fallback_solver

    return fallback_solver.solve(data)


def solve(data: dict) -> dict:
    time_limit, workers = _settings()
    n_days, n_slots = len(data["days"]), len(data["slots"])
    times = [(d, s) for d in range(n_days) for s in range(n_slots)]
    options = data.get("options", {})
    max_group_day = options.get("max_sessions_per_day_group", n_slots)
    max_prof_day = options.get("max_sessions_per_day_prof", n_slots)

    profs = {p["id"]: p for p in data["professors"]}
    unavailable = {(p["id"], d, s) for p in data["professors"] for d, s in p.get("unavailable", [])}
    avoid = {(p["id"], d, s) for p in data["professors"] for d, s in p.get("avoid", [])}
    teachers = defaultdict(set)  # (module_id, kind) -> {prof_id}
    rank = {}
    for t in data["can_teach"]:
        rank[(t["prof_id"], t["module_id"])] = t.get("rank", 1)
        for k in t["kinds"]:
            if t["prof_id"] in profs:
                teachers[(t["module_id"], k)].add(t["prof_id"])

    # Group tree: a group clashes with its ancestors (a lecture blocks its groups).
    parent = {g["id"]: g.get("parent_id") for g in data["groups"]}
    has_child = {g.get("parent_id") for g in data["groups"]}
    leaves = [gid for gid in parent if gid not in has_child]

    def chain(gid):
        out = []
        while gid is not None:
            out.append(gid)
            gid = parent.get(gid)
        return out

    reqs = data["requirements"]
    bundles = defaultdict(list)  # same module, kind and group -> same professor
    for r in reqs:
        bundles[(r["module_id"], r["kind"], r["group_id"])].append(r)

    # Interchangeable rooms: same type and same number of seats.
    classes = defaultdict(list)  # (type, capacity) -> [room ids]
    for rm in data["rooms"]:
        classes[(rm["type"], rm["capacity"])].append(rm["id"])
    class_of_room = {rid: c for c, ids in classes.items() for rid in ids}

    model = cp_model.CpModel()
    w = {}  # (req, prof, t) -> professor + time chosen
    x = {}  # (req, t, room class) -> time + room class chosen
    skip = {}  # req -> left out of the timetable
    reason = {}
    penalties = []

    for key, items in bundles.items():
        module_id, kind, _ = key
        cands = sorted(p for p in teachers[(module_id, kind)] if profs[p].get("max_sessions", 1) > 0)
        rooms = [c for c in classes
                 if c[0] in data["room_types_for"].get(kind, []) and c[1] >= items[0]["size"]]
        if not cands:
            for r in items:
                reason[r["id"]] = "no professor can teach this module/kind"
        elif not rooms:
            for r in items:
                reason[r["id"]] = "no open room of the right type with enough seats"
        y = {p: model.NewBoolVar("") for p in cands}
        if cands and rooms:
            model.AddExactlyOne(y.values())
            for p in cands:
                penalties.append(WEIGHTS["rank"] * (rank.get((p, module_id), 1) - 1) * len(items) * y[p])
        allowed = data["room_types_for"].get(kind, [])
        for r in items:
            rid = r["id"]
            skip[rid] = model.NewBoolVar("")
            penalties.append(WEIGHTS["unscheduled"] * skip[rid])
            if not (cands and rooms):
                model.Add(skip[rid] == 1)
                continue
            chosen = [skip[rid]]
            for ti, (d, s) in enumerate(times):
                at_t = []
                for p in cands:
                    if (p, d, s) in unavailable:
                        continue
                    v = model.NewBoolVar("")
                    model.AddImplication(v, y[p])
                    w[rid, p, ti] = v
                    at_t.append(v)
                    if (p, d, s) in avoid:
                        penalties.append(WEIGHTS["avoid"] * v)
                if not at_t:
                    continue
                in_room = []
                for c in rooms:
                    v = model.NewBoolVar("")
                    x[rid, ti, c] = v
                    in_room.append(v)
                    if allowed.index(c[0]):
                        penalties.append(WEIGHTS["room_type"] * allowed.index(c[0]) * v)
                model.Add(sum(at_t) == sum(in_room))
                chosen.extend(at_t)
            model.AddExactlyOne(chosen)

    # Indexes for the "one thing at a time" rules.
    occ = defaultdict(list)  # (req, t) -> professor/time variables (sum = 1 if placed at t)
    by_prof, by_prof_day, by_prof_all = defaultdict(list), defaultdict(list), defaultdict(list)
    for (rid, p, ti), v in w.items():
        occ[rid, ti].append(v)
        by_prof[p, ti].append(v)
        by_prof_day[p, times[ti][0]].append(v)
        by_prof_all[p].append(v)
    by_class = defaultdict(list)
    for (rid, ti, c), v in x.items():
        by_class[c, ti].append(v)

    for vs in by_prof.values():
        if len(vs) > 1:
            model.AddAtMostOne(vs)
    for (c, ti), vs in by_class.items():  # no more sessions than rooms of that class
        if len(vs) > len(classes[c]):
            model.Add(sum(vs) <= len(classes[c]))
    for p, vs in by_prof_all.items():
        model.Add(sum(vs) <= profs[p].get("max_sessions", len(times)))
    for vs in by_prof_day.values():
        if len(vs) > max_prof_day:
            model.Add(sum(vs) <= max_prof_day)

    # Students: for each smallest group, its own sessions + its ancestors' sessions.
    reqs_of_group = defaultdict(list)
    for r in reqs:
        reqs_of_group[r["group_id"]].append(r["id"])
    for leaf in leaves:
        mine = [rid for g in chain(leaf) for rid in reqs_of_group[g]]
        if not mine:
            continue
        for d in range(n_days):
            day_vars, occupied = [], []
            for s in range(n_slots):
                ti = d * n_slots + s
                vs = [v for rid in mine for v in occ.get((rid, ti), [])]
                if len(vs) > 1:
                    model.AddAtMostOne(vs)
                day_vars.extend(vs)
                occupied.append(sum(vs) if vs else 0)
                if s == n_slots - 1 and vs:
                    penalties.append(WEIGHTS["late"] * sum(vs))
            if not day_vars:
                continue
            if len(day_vars) > max_group_day:
                model.Add(sum(day_vars) <= max_group_day)
            # gaps = (last - first + 1) - number of classes, when the day is not empty
            count = sum(day_vars)
            busy = model.NewBoolVar("")
            model.Add(count >= 1).OnlyEnforceIf(busy)
            model.Add(count == 0).OnlyEnforceIf(busy.Not())
            first = model.NewIntVar(0, n_slots - 1, "")
            last = model.NewIntVar(0, n_slots - 1, "")
            for s, o in enumerate(occupied):
                if isinstance(o, int):
                    continue
                model.Add(first <= s + n_slots * (1 - o))
                model.Add(last >= s * o)
            gaps = model.NewIntVar(0, n_slots, "")
            model.Add(gaps >= last - first + 1 - count - n_slots * (1 - busy))
            penalties.append(WEIGHTS["gap"] * gaps)

    # The same module twice on one day for a group: spread it over the week.
    for items in bundles.values():
        if len(items) < 2:
            continue
        for d in range(n_days):
            vs = [v for r in items for s in range(n_slots) for v in occ.get((r["id"], d * n_slots + s), [])]
            if len(vs) > 1:
                extra = model.NewIntVar(0, len(items), "")
                model.Add(extra >= sum(vs) - 1)
                penalties.append(WEIGHTS["same_day"] * extra)

    # Fewest changes: reward keeping a session where it was (same professor, time and room).
    previous = {p["requirement_id"]: p for p in data.get("previous", [])}
    for rid, prev in previous.items():
        ti = prev["day"] * n_slots + prev["slot"] if prev["slot"] < n_slots else None
        same_time = w.get((rid, prev["prof_id"], ti))
        same_room = x.get((rid, ti, class_of_room.get(prev["room_id"])))
        if same_time is None or same_room is None:
            penalties.append(WEIGHTS["moved"])  # its place no longer exists: it has to move
            continue
        keep = model.NewBoolVar("")
        model.AddImplication(keep, same_time)
        model.AddImplication(keep, same_room)
        penalties.append(WEIGHTS["moved"] * (1 - keep))

    model.Minimize(sum(penalties))

    # Start the search from the greedy solver's result: it is valid and already keeps the
    # current timetable where it can, so the search only has to improve it. Every choice
    # variable gets a hint (1 = what the greedy result did, 0 = the rest).
    greedy = _greedy_start(data)
    chosen_w = {(a["requirement_id"], a["prof_id"], a["day"] * n_slots + a["slot"]) for a in greedy}
    chosen_x = {(a["requirement_id"], a["day"] * n_slots + a["slot"], class_of_room.get(a["room_id"]))
                for a in greedy}
    if greedy:
        for key, v in w.items():
            model.AddHint(v, key in chosen_w)
        for key, v in x.items():
            model.AddHint(v, key in chosen_x)
        placed_ids = {a["requirement_id"] for a in greedy}
        for rid, v in skip.items():
            model.AddHint(v, rid not in placed_ids)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = workers
    solver.parameters.random_seed = 7
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"CP-SAT found no timetable within {time_limit:.0f} s "
                           f"(status {solver.StatusName(status)})")
    n_skipped = sum(solver.Value(v) for v in skip.values())
    if greedy and len(reqs) - n_skipped < len(greedy):
        # Safety net: with too little time the search may end on a worse timetable than its
        # starting point. Never place fewer sessions than the greedy solver did.
        result = _greedy_full(data)
        result["stats"] = {"status": "KEPT_GREEDY_START", "seconds": round(solver.WallTime(), 2)}
        return result

    assignments, unscheduled = [], []
    placed = {}
    for (rid, p, ti), v in w.items():
        if solver.Value(v):
            placed[rid] = (p, ti)
    room_of = _pick_rooms(x, solver, classes, previous, n_slots)
    for r in reqs:
        rid = r["id"]
        if rid in placed:
            p, ti = placed[rid]
            d, s = times[ti]
            assignments.append({"requirement_id": rid, "prof_id": p, "room_id": room_of[rid, ti],
                                "day": d, "slot": s})
        else:
            unscheduled.append({"requirement_id": rid, "reason": reason.get(
                rid, "no free slot with a free professor and room")})
    return {"assignments": assignments, "unscheduled": unscheduled,
            "stats": {"status": solver.StatusName(status), "objective": solver.ObjectiveValue(),
                      "best_bound": solver.BestObjectiveBound(),
                      "seconds": round(solver.WallTime(), 2)}}


def _pick_rooms(x, solver, classes, previous, n_slots):
    """Turn each chosen room class into an actual room: a session keeps its previous room when
    that room is still free at that time, the others take the remaining rooms of the class."""
    wanted = defaultdict(list)  # (class, t) -> [requirement ids]
    for (rid, ti, c), v in x.items():
        if solver.Value(v):
            wanted[c, ti].append(rid)
    room_of = {}
    for (c, ti), rids in wanted.items():
        free = list(classes[c])
        rest = []
        for rid in rids:
            prev = previous.get(rid)
            if prev and prev["day"] * n_slots + prev["slot"] == ti and prev["room_id"] in free:
                room_of[rid, ti] = prev["room_id"]
                free.remove(prev["room_id"])
            else:
                rest.append(rid)
        for rid in rest:
            room_of[rid, ti] = free.pop(0)
    return room_of
