"""A realistic but 100% synthetic computer-science department, for the demo and the tests.

Names are invented. Loads are in 1h30 sessions per week: (lecture, td, tp).
"""
import math
from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DB

from .models import (
    Absence,
    Claim,
    Group,
    Level,
    Module,
    Professor,
    Room,
    Session,
    Teaching,
    Unavailability,
    User,
)
from .rules import Rules, get_rules
from .services.catalog import create_professor

LEVELS = {
    "L1 CS": (160, {
        "Algorithms 1": (2, 2, 1), "Calculus 1": (2, 2, 0), "Linear Algebra 1": (1, 2, 0),
        "Computer Structure": (1, 1, 1), "Terminology": (1, 0, 0), "English 1": (0, 1, 0)}),
    "L2 CS": (120, {
        "Algorithms & Data Structures": (2, 1, 1), "Computer Architecture": (1, 1, 1),
        "Information Systems": (1, 1, 0), "Formal Languages": (1, 1, 0),
        "Probability": (1, 1, 0), "Object-Oriented Programming": (1, 0, 1)}),
    "L3 ISIL": (70, {
        "Software Engineering": (1, 1, 1), "Compilers": (1, 1, 1), "Networks": (1, 1, 1),
        "Databases": (1, 1, 1), "Human-Computer Interaction": (1, 0, 1)}),
    "L3 SI": (60, {
        "Operating Systems 2": (1, 1, 1), "Operations Research": (1, 1, 0),
        "Computer Security": (1, 1, 1), "Data Mining": (1, 0, 1)}),
    "M1 AI": (40, {
        "Machine Learning": (1, 1, 1), "Computer Vision": (1, 0, 1),
        "Optimization": (1, 1, 0), "Natural Language Processing": (1, 0, 1)}),
    "M2 AI": (30, {
        "Deep Learning": (1, 0, 1), "Project Methodology": (0, 1, 0), "AI Ethics": (1, 0, 0)}),
    "M1 SEC": (35, {
        "Applied Cryptography": (1, 1, 1), "Network Security": (1, 1, 1),
        "Secure Software Development": (1, 0, 1), "Security Auditing & Standards": (1, 1, 0)}),
    "M2 SEC": (28, {
        "Penetration Testing": (1, 0, 1), "Digital Forensics": (1, 0, 1),
        "Cloud & IoT Security": (1, 1, 0), "Research Methodology": (0, 1, 0)}),
}

ROOMS = (
    [("Amphi A", "amphi", 220), ("Amphi B", "amphi", 150)]
    + [(f"Room {i}", "td", 40) for i in range(1, 13)]
    + [(f"Lab {i}", "lab", 32) for i in range(1, 8)]
)

PROF_NAMES = [
    "Amel Kaci", "Yacine Hamdi", "Nadia Bouzid", "Karim Mansouri", "Samia Ferhat",
    "Rachid Belaid", "Lina Saadi", "Omar Touati", "Meriem Cherif", "Sofiane Rahal",
    "Imane Zerrouki", "Walid Messaoudi", "Hania Brahimi", "Fares Lounis", "Dalila Amrani",
    "Mehdi Benyahia", "Sarah Khelifi", "Nabil Ouali", "Asma Djebbar", "Tarek Hadj",
    "Yasmine Larbi", "Hichem Saidi", "Kenza Mebarki", "Bilal Aouadi", "Rym Bensaid",
    "Anis Guerfi", "Selma Rezki", "Zakaria Mokrani", "Leila Boukhari", "Islem Naceur",
    "Ines Taleb", "Riad Boudjema", "Chahinez Ait Ali", "Mounir Zitouni", "Sabrina Hamidi",
    "Adel Benamara", "Nesrine Kherbache", "Hamza Belkacem", "Amira Sellami", "Yanis Ouchene",
]  # invented names


def clear_all(db: DB) -> None:
    for model in (Claim, Absence, Session, Unavailability, Teaching, Group, Module, Level, Room):
        db.execute(delete(model))
    db.execute(delete(User).where(User.role == "prof"))
    db.execute(delete(Professor))
    db.commit()


def _group_counts(headcount: int, rules: Rules) -> tuple[int, int, int]:
    """(#sections, #TD groups, #groups doing TP) using the same rules as build_groups."""
    n_sec = max(1, math.ceil(headcount / rules.section_max_size))
    n_td, n_tp = 0, 0
    for s in range(n_sec):
        s_size = headcount // n_sec + (1 if s < headcount % n_sec else 0)
        k = max(1, math.ceil(s_size / rules.td_group_size))
        n_td += k
        for t in range(k):
            t_size = s_size // k + (1 if t < s_size % k else 0)
            n_tp += max(1, math.ceil(t_size / rules.tp_group_size)) if rules.split_tp_groups else 1
    return n_sec, n_td, n_tp


def is_empty(db: DB) -> bool:
    return not any(db.scalar(select(m.id).limit(1)) for m in (Room, Level, Module, Professor))


def seed_demo(db: DB) -> dict:
    """Load the synthetic department. The caller makes sure the database is empty first."""
    clear_all(db)
    rules = get_rules(db)
    max_sessions = rules.default_max_sessions_per_professor
    for name, rtype, cap in ROOMS:
        db.add(Room(name=name, type=rtype, capacity=cap))

    # Work out how many sessions each (module, kind) needs, then hand them to professors.
    needs = []  # (module, kind, sessions)
    for level_name, (headcount, modules) in LEVELS.items():
        level = Level(name=level_name, headcount=headcount)
        db.add(level)
        db.flush()
        n_sec, n_td, n_tp = _group_counts(headcount, rules)
        for mod_name, (lec, td, tp) in modules.items():
            m = Module(level_id=level.id, name=mod_name, lecture_per_week=lec,
                       td_per_week=td, tp_per_week=tp)
            db.add(m)
            db.flush()
            for kind, total in (("lecture", lec * n_sec), ("td", td * n_td), ("tp", tp * n_tp)):
                if total:
                    needs.append((m, kind, total))

    profs, credentials = [], []
    names = iter(PROF_NAMES)
    load = defaultdict(int)
    teach = defaultdict(set)  # prof index -> {(module_id, kind)}
    target = int(max_sessions * 0.75)  # leave slack so the solver has room to move
    for m, kind, total in sorted(needs, key=lambda x: -x[2]):
        remaining = total
        # Each (module, kind) gets at least 2 professors when it is big, for flexibility.
        while remaining > 0:
            idx = next((i for i in range(len(profs)) if load[i] + 1 <= target
                        and (m.id, kind) not in teach[i]), None)
            if idx is None:
                name = next(names, None) or f"Enseignant {len(profs) + 1}"
                p, username, password = create_professor(db, name, max_sessions)
                profs.append(p)
                credentials.append({"name": p.name, "username": username, "password": password})
                idx = len(profs) - 1
            take = min(remaining, target - load[idx])
            load[idx] += take
            teach[idx].add((m.id, kind))
            remaining -= take
    for idx, pairs in teach.items():
        by_module = defaultdict(list)
        for mid, kind in sorted(pairs):
            by_module[mid].append(kind)
        # Wish-list order: the module with the most sessions first.
        ordered = sorted(by_module, key=lambda mid: -len(by_module[mid]))
        for rank, mid in enumerate(ordered, start=1):
            db.add(Teaching(professor_id=profs[idx].id, module_id=mid,
                            kinds=",".join(by_module[mid]), rank=rank))
    # A few realistic constraints: some professors can't teach on Thursday afternoon,
    # others would rather not start at 8:00.
    n_slots, n_days = rules.n_slots, rules.n_days
    for idx, p in enumerate(profs):
        if idx % 4 == 1 and n_days >= 1 and n_slots >= 2:
            for slot in (n_slots - 2, n_slots - 1):
                db.add(Unavailability(professor_id=p.id, day=n_days - 1, slot=slot))
        if idx % 3 == 2:
            for day in range(n_days):
                db.add(Unavailability(professor_id=p.id, day=day, slot=0, soft=True))
    db.commit()
    return {"levels": len(LEVELS), "rooms": len(ROOMS), "professors": len(profs),
            "credentials": credentials}
