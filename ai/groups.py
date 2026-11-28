"""
Group builder.

Turns level headcounts into sections and groups, and lists the sessions
each group must have per week. No student names are used, only headcounts.
Used by the solver (real data) and by generate.py (mock data).

    Section 1        -> attends lectures (Cours) in an amphi
      G1, G2, G3 ... -> at most 40 students, attends TD in a TD room
                        and TP in a lab (the whole group goes to the lab)

Clash rule for the solver: a group must not have two sessions in the same
slot, AND a lecture of a section blocks all its groups.
Use `family(group_id, groups)` to get every group that clashes with a given one.

Usage:
    python groups.py out/department_real.json   # writes out/groups_real.json
"""
import json
import math
import sys
from collections import defaultdict


def split_evenly(total, parts):
    """Split `total` students into `parts` sizes that differ by at most 1."""
    base, extra = divmod(total, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


def n_parts(size, target, maximum):
    """How many groups: close to `target` students each, never above `maximum`.
    e.g. 240 students, max 40 -> 6 groups of 40; 90 students -> 3 groups of 30."""
    n = max(1, round(size / target))
    while math.ceil(size / n) > maximum:
        n += 1
    return n


def build_groups(dept):
    """Naming:
        section  L1-INFO-S1      "L1 INFO · Section 1"
        group    L1-INFO-S1-G3   "L1 INFO · G3"
    Groups are numbered across the whole level: if Section 1 has G1-G4,
    Section 2 continues with G5-G8, so "G6" is unique inside a level.
    """
    rules = dept["rules"]
    groups = []
    for level in dept["levels"]:
        short = f"{level['year']} {level['speciality']}"     # "L3 ISIL"
        base = {"level": level["id"], "year": level["year"], "speciality": level["speciality"]}
        g_num = 0                                             # G counter for the whole level
        n_sec = math.ceil(level["headcount"] / rules["section_max"])
        for si, sec_size in enumerate(split_evenly(level["headcount"], n_sec), 1):
            sec_id = f"{level['id']}-S{si}"
            groups.append({"id": sec_id, "name": f"{short} · Section {si}", **base,
                           "kind": "section", "parent": None, "size": sec_size})
            n_groups = n_parts(sec_size, rules["group_size"], rules["group_max"])
            for g_size in split_evenly(sec_size, n_groups):
                g_num += 1
                groups.append({"id": f"{sec_id}-G{g_num}", "name": f"{short} · G{g_num}", **base,
                               "kind": "group", "parent": sec_id, "size": g_size})
    return groups


def session_demand(dept, groups):
    """List of (module, kind, group) sessions to teach per week.
    A lecture is for a section, a TD or TP for each group of that section.
    e.g. L1 module with 1 lecture + 1 TD and 6 groups -> 1 + 6 = 7 sessions."""
    demand = []
    by_level = defaultdict(list)
    for g in groups:
        by_level[(g["level"], g["kind"])].append(g)
    kind_group = {"lecture": "section", "td": "group", "tp": "group"}
    for m in dept["modules"]:
        for kind, per_week in m["weekly"].items():
            for g in by_level[(m["level"], kind_group[kind])]:
                demand += [(m["id"], kind, g["id"])] * per_week
    return demand


def family(group_id, groups):
    """All groups that clash with `group_id`: itself, its ancestors, its descendants.
    A section's family = the section + all its groups.
    A group's family   = the group + its section."""
    by_id = {g["id"]: g for g in groups}
    result = {group_id}
    g = by_id[group_id]
    while g["parent"]:                      # walk up
        result.add(g["parent"])
        g = by_id[g["parent"]]
    frontier = [group_id]
    while frontier:                         # walk down
        cur = frontier.pop()
        for child in (x for x in groups if x["parent"] == cur):
            result.add(child["id"])
            frontier.append(child["id"])
    return result


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "out/department_real.json"
    with open(src, encoding="utf-8") as f:
        dept = json.load(f)
    groups = build_groups(dept)
    out = src.replace("department", "groups")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(groups, f, ensure_ascii=False, indent=2)
    n_sec = sum(g["kind"] == "section" for g in groups)
    n_grp = sum(g["kind"] == "group" for g in groups)
    print(f"{out}: {n_sec} sections, {n_grp} groups")
