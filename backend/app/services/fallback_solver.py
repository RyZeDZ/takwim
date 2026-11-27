"""The built-in greedy timetable solver, used when no AI solver plug-in is configured.

It follows the same contract as a plug-in (see solver_adapter.py), so it doubles as a
reference implementation. It is fast and always respects the hard rules, and it keeps
sessions where they were when it can (fewest changes). It is not optimal: a CP-SAT solver
should give fewer gaps and better balance.
"""
from collections import defaultdict

KIND_ORDER = {"lecture": 0, "td": 1, "tp": 2}


def _related_sets(groups: list[dict]) -> dict[int, set[int]]:
    parent = {g["id"]: g.get("parent_id") for g in groups}
    children = defaultdict(list)
    for g in groups:
        if g.get("parent_id") is not None:
            children[g["parent_id"]].append(g["id"])
    out = {}
    for gid in parent:
        rel = {gid}
        p = parent.get(gid)
        while p is not None:
            rel.add(p)
            p = parent.get(p)
        stack = list(children[gid])
        while stack:
            c = stack.pop()
            rel.add(c)
            stack.extend(children[c])
        out[gid] = rel
    return out


def solve(data: dict) -> dict:
    n_days, n_slots = len(data["days"]), len(data["slots"])
    max_per_day = data.get("options", {}).get("max_sessions_per_day_group", 4)
    room_types_for = data["room_types_for"]
    related = _related_sets(data["groups"])
    rooms = data["rooms"]
    profs = {p["id"]: p for p in data["professors"]}
    unavailable = {(p["id"], d, s) for p in data["professors"] for d, s in p.get("unavailable", [])}

    teachers = defaultdict(list)  # (module_id, kind) -> [prof_id]
    for t in data["can_teach"]:
        for k in t["kinds"]:
            teachers[(t["module_id"], k)].append(t["prof_id"])

    previous = {p["requirement_id"]: p for p in data.get("previous", [])}
    req_group = {r["id"]: r["group_id"] for r in data["requirements"]}
    # Places held in the previous timetable by requirements not placed yet in this run:
    # avoid taking them, so that one moved session doesn't push all the others around.
    held_room, held_prof, held_group = {}, {}, defaultdict(set)
    for rid, p in previous.items():
        if rid in req_group:
            held_room[(p["room_id"], p["day"], p["slot"])] = rid
            held_prof[(p["prof_id"], p["day"], p["slot"])] = rid
            held_group[(req_group[rid], p["day"], p["slot"])].add(rid)
    placed_ids = set()

    def held_by_other(table, key, rid):
        other = table.get(key)
        return other is not None and other != rid and other not in placed_ids
    load = defaultdict(int)
    prof_busy, room_busy = set(), set()
    group_slots = defaultdict(set)  # (group_id, day) -> {slots}
    module_days = defaultdict(lambda: defaultdict(int))  # (module, group, kind) -> {day: n}

    bundles = defaultdict(list)
    for r in data["requirements"]:
        bundles[(r["module_id"], r["kind"], r["group_id"])].append(r)
    order = sorted(
        bundles.items(),
        key=lambda kv: (KIND_ORDER.get(kv[0][1], 9), -kv[1][0]["size"],
                        len(teachers[(kv[0][0], kv[0][1])])),
    )

    def day_count(gid, d):
        return sum(len(group_slots[(rg, d)]) for rg in related[gid])

    def best_place(req, pid):
        gid, size, kind = req["group_id"], req["size"], req["kind"]
        prev = previous.get(req["id"])
        if prev and prev["prof_id"] != pid:
            prev = None
        if load[pid] >= profs[pid].get("max_sessions", 99):
            return None
        allowed = room_types_for.get(kind, [])
        best = None
        for d in range(n_days):
            dc = day_count(gid, d)
            for s in range(n_slots):
                if (pid, d, s) in prof_busy or (pid, d, s) in unavailable:
                    continue
                if any(s in group_slots[(rg, d)] for rg in related[gid]):
                    continue
                room, room_cost = None, None
                for rm in rooms:
                    if rm["type"] not in allowed or rm["capacity"] < size:
                        continue
                    if (rm["id"], d, s) in room_busy:
                        continue
                    cost = allowed.index(rm["type"]) * 5 + (rm["capacity"] - size) / 10
                    if prev and (prev["day"], prev["slot"], prev["room_id"]) == (d, s, rm["id"]):
                        cost -= 50  # same place as in the previous timetable
                    if held_by_other(held_room, (rm["id"], d, s), req["id"]):
                        cost += 30
                    if room_cost is None or cost < room_cost:
                        room, room_cost = rm, cost
                if room is None:
                    continue
                adjacent = any((s - 1) in group_slots[(rg, d)] or (s + 1) in group_slots[(rg, d)]
                               for rg in related[gid])
                score = (
                    dc * 10
                    + (100 if dc >= max_per_day else 0)
                    + (30 if module_days[(req["module_id"], gid, kind)][d] > 0 else 0)
                    + room_cost
                    + s
                    - (8 if adjacent else 0)
                    - (40 if prev and (prev["day"], prev["slot"]) == (d, s) else 0)
                    + (30 if held_by_other(held_prof, (pid, d, s), req["id"]) else 0)
                    + (30 if any(o != req["id"] and o not in placed_ids
                                 for rg in related[gid] for o in held_group.get((rg, d, s), ()))
                       else 0)
                )
                if best is None or score < best[0]:
                    best = (score, d, s, room["id"])
        return best

    def place(req, pid, d, s, rid):
        placed_ids.add(req["id"])
        prof_busy.add((pid, d, s))
        room_busy.add((rid, d, s))
        group_slots[(req["group_id"], d)].add(s)
        module_days[(req["module_id"], req["group_id"], req["kind"])][d] += 1
        load[pid] += 1

    def unplace(req, pid, d, s, rid):
        placed_ids.discard(req["id"])
        prof_busy.discard((pid, d, s))
        room_busy.discard((rid, d, s))
        group_slots[(req["group_id"], d)].discard(s)
        module_days[(req["module_id"], req["group_id"], req["kind"])][d] -= 1
        load[pid] -= 1

    assignments, unscheduled = [], []
    for (module_id, kind, gid), reqs in order:
        prev_profs = {previous[r["id"]]["prof_id"] for r in reqs if r["id"] in previous}
        candidates = sorted(set(teachers[(module_id, kind)]),
                            key=lambda p: (p not in prev_profs,
                                           load[p] / max(1, profs[p].get("max_sessions", 12))))
        if not candidates:
            for r in reqs:
                unscheduled.append({"requirement_id": r["id"],
                                    "reason": "no professor can teach this module/kind"})
            continue
        chosen, best_partial = None, []
        for pid in candidates:
            placed = []
            for r in reqs:
                spot = best_place(r, pid)
                if spot is None:
                    break
                _, d, s, rid = spot
                place(r, pid, d, s, rid)
                placed.append((r, pid, d, s, rid))
            if len(placed) == len(reqs):
                chosen = placed
                break
            for p in reversed(placed):  # undo, try the next professor
                unplace(*p)
            if len(placed) > len(best_partial):
                best_partial = placed
        if chosen is None:
            # Nobody could take the whole bundle: keep the best partial attempt.
            for p in best_partial:
                place(*p)
            chosen = best_partial
        for r, pid, d, s, rid in chosen:
            assignments.append({"requirement_id": r["id"], "prof_id": pid,
                                "room_id": rid, "day": d, "slot": s})
        done = {r["id"] for r, *_ in chosen}
        for r in reqs:
            if r["id"] not in done:
                unscheduled.append({"requirement_id": r["id"],
                                    "reason": "no free slot with a free professor and room"})
    return {"assignments": assignments, "unscheduled": unscheduled}
