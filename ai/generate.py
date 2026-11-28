"""
Synthetic department generator.

Creates a fake but realistic computer-science department:
    L1, L2            common core (Informatique)
    L3                2 specialities: ISIL, SI
    M1, M2            5 specialities: IA, SECU, GL, DS, RES
with headcounts, rooms, modules, professors with vœux (preferences), and
the slots each professor is unavailable. No real people, no student names.

Outputs (in ./out by default):
    department_<size>.json   clean data in the team's JSON format (see README.md)
    groups_<size>.json       sections and groups (G1, G2...) built from headcounts
    messy_<size>/*.csv       the same data with messy French headers, as a
                             department would send it (to test the importer)
    messy_<size>.xlsx        same messy data as one Excel workbook
    messy_<size>/columns_truth.json   correct header -> field mapping
                             (to score the column mapper)

Usage:
    python generate.py                      # real size, seed 42
    python generate.py --size small         # tiny dataset for debugging
    python generate.py --size real --seed 7 # another department

Only the Python standard library is needed (openpyxl is optional, for .xlsx).
"""
import argparse
import csv
import json
import os
import random
from collections import defaultdict

from groups import build_groups, session_demand

# --------------------------------------------------------------------------
# Fixed reference data
# --------------------------------------------------------------------------
# the admin chooses the study week: Saturday-Thursday or Sunday-Thursday (--week sat / sun)
WEEKS = {"sat": ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"],
         "sun": ["Sun", "Mon", "Tue", "Wed", "Thu"]}
DAYS_FR = {"Sat": "Samedi", "Sun": "Dimanche", "Mon": "Lundi", "Tue": "Mardi",
           "Wed": "Mercredi", "Thu": "Jeudi"}
SLOTS = [("08:00", "09:30"), ("09:30", "11:00"), ("11:00", "12:30"),
         ("12:30", "14:00"), ("14:00", "15:30"), ("15:30", "17:00")]

FIRST = ["Ahmed", "Karim", "Yacine", "Samir", "Nadia", "Amina", "Fatima", "Leila",
         "Sofiane", "Rachid", "Meriem", "Sara", "Imane", "Hichem", "Walid", "Nour",
         "Salima", "Mourad", "Djamel", "Khadija", "Omar", "Youssef", "Hind", "Zineb",
         "Anis", "Lamia", "Bilal", "Asma", "Redouane", "Souad", "Abdelkader", "Nassima",
         "Fares", "Rym", "Mehdi", "Wafa", "Lotfi", "Chahrazed", "Islam", "Selma"]
LAST = ["Benali", "Boudiaf", "Haddad", "Mansouri", "Cherif", "Belkacem", "Saidi",
        "Amrani", "Bouzid", "Meziane", "Hamidi", "Rahmani", "Toumi", "Ziani", "Kaci",
        "Brahimi", "Lahlou", "Bennani", "Idrissi", "Tazi", "Alaoui", "Chaoui",
        "Benyahia", "Ouali", "Slimani", "Djebbar", "Mekki", "Ferhat", "Hadjadj",
        "Benmoussa", "Guerfi", "Yahiaoui", "Boukhalfa", "Larbi", "Khelifi", "Sahraoui"]

# Levels: id -> (year, speciality code, display name)
LEVELS = {
    "L1-INFO": ("L1", "INFO", "Licence 1 Informatique (tronc commun)"),
    "L2-INFO": ("L2", "INFO", "Licence 2 Informatique (tronc commun)"),
    "L3-ISIL": ("L3", "ISIL", "Licence 3 Ingénierie des Systèmes d'Information et du Logiciel"),
    "L3-SI":   ("L3", "SI",   "Licence 3 Systèmes Informatiques"),
    "M1-IA":   ("M1", "IA",   "Master 1 Intelligence Artificielle"),
    "M1-SECU": ("M1", "SECU", "Master 1 Sécurité Informatique"),
    "M1-GL":   ("M1", "GL",   "Master 1 Génie Logiciel"),
    "M1-DS":   ("M1", "DS",   "Master 1 Data Science"),
    "M1-RES":  ("M1", "RES",  "Master 1 Réseaux"),
    "M2-IA":   ("M2", "IA",   "Master 2 Intelligence Artificielle"),
    "M2-SECU": ("M2", "SECU", "Master 2 Sécurité Informatique"),
    "M2-GL":   ("M2", "GL",   "Master 2 Génie Logiciel"),
    "M2-DS":   ("M2", "DS",   "Master 2 Data Science"),
    "M2-RES":  ("M2", "RES",  "Master 2 Réseaux"),
}

# Modules per level: (code, name, td per week, tp per week, theme)
# Every module has 1 lecture per week.
MODULES = {
    "L1-INFO": [("ASD1", "Algorithmique et structures de données 1", 1, 1, "prog"),
                ("ANA1", "Analyse 1", 1, 0, "math"),
                ("ALG1", "Algèbre 1", 1, 0, "math"),
                ("ARCH", "Architecture des ordinateurs", 1, 0, "sys"),
                ("ISE", "Introduction aux systèmes d'exploitation", 1, 1, "sys"),
                ("TS", "Terminologie scientifique", 0, 0, "misc"),
                ("BUR", "Bureautique", 0, 1, "misc")],
    "L2-INFO": [("ASD2", "Algorithmique et structures de données 2", 1, 1, "prog"),
                ("SIG", "Systèmes d'information", 1, 0, "data"),
                ("THL", "Théorie des langages", 1, 0, "math"),
                ("PROBA", "Probabilités et statistiques", 1, 0, "math"),
                ("POO", "Programmation orientée objet", 1, 1, "prog"),
                ("RES1", "Réseaux 1", 1, 0, "net"),
                ("LOG", "Logique mathématique", 1, 0, "math")],
    "L3-ISIL": [("GL", "Génie logiciel", 1, 0, "prog"),
                ("BDD", "Bases de données", 1, 1, "data"),
                ("ACSI", "Analyse et conception des SI (UML)", 1, 0, "data"),
                ("WEB", "Programmation web", 0, 1, "prog"),
                ("IHM", "Interfaces homme-machine", 0, 1, "prog"),
                ("RO", "Recherche opérationnelle", 1, 0, "math"),
                ("ECO", "Économie et gestion de l'entreprise", 0, 0, "misc")],
    "L3-SI":   [("SE2", "Systèmes d'exploitation 2", 1, 1, "sys"),
                ("COMP", "Compilation", 1, 1, "prog"),
                ("RES2", "Réseaux 2", 1, 1, "net"),
                ("ARCH2", "Architecture avancée des ordinateurs", 1, 0, "sys"),
                ("PL", "Programmation linéaire", 1, 0, "math"),
                ("IA", "Introduction à l'intelligence artificielle", 1, 0, "ai"),
                ("ANG", "Anglais technique", 0, 0, "misc")],
    "M1-IA":   [("ML", "Apprentissage automatique", 1, 1, "ai"),
                ("RCR", "Représentation des connaissances et raisonnement", 1, 0, "ai"),
                ("VA", "Vision artificielle", 1, 1, "ai"),
                ("META", "Optimisation et métaheuristiques", 1, 0, "math"),
                ("ALGA", "Algorithmique avancée", 1, 0, "prog"),
                ("ANG", "Anglais scientifique", 0, 0, "misc")],
    "M1-SECU": [("CRYP", "Cryptographie", 1, 1, "sec"),
                ("SRES", "Sécurité des réseaux", 1, 1, "sec"),
                ("MCRY", "Mathématiques pour la cryptographie", 1, 0, "math"),
                ("SEA", "Systèmes d'exploitation avancés", 1, 0, "sys"),
                ("AUD", "Audit et normes de sécurité", 1, 0, "sec"),
                ("ANG", "Anglais scientifique", 0, 0, "misc")],
    "M1-GL":   [("ARCL", "Architecture logicielle", 1, 0, "prog"),
                ("MF", "Méthodes formelles", 1, 0, "math"),
                ("QTL", "Qualité et test logiciel", 1, 1, "prog"),
                ("MOB", "Développement mobile", 0, 1, "prog"),
                ("GLA", "Génie logiciel avancé", 1, 1, "prog"),
                ("ANG", "Anglais scientifique", 0, 0, "misc")],
    "M1-DS":   [("STA", "Statistiques avancées", 1, 1, "math"),
                ("FD", "Fouille de données", 1, 1, "data"),
                ("BDA", "Bases de données avancées", 1, 1, "data"),
                ("ML", "Apprentissage automatique", 1, 1, "ai"),
                ("VIZ", "Visualisation de données", 0, 1, "data"),
                ("ANG", "Anglais scientifique", 0, 0, "misc")],
    "M1-RES":  [("RA", "Réseaux avancés", 1, 1, "net"),
                ("ASR", "Administration systèmes et réseaux", 0, 1, "net"),
                ("RSF", "Réseaux sans fil et mobiles", 1, 0, "net"),
                ("SD", "Systèmes distribués", 1, 0, "sys"),
                ("EVP", "Évaluation de performances", 1, 0, "math"),
                ("ANG", "Anglais scientifique", 0, 0, "misc")],
    "M2-IA":   [("DL", "Deep learning", 1, 1, "ai"),
                ("NLP", "Traitement automatique du langage", 1, 1, "ai"),
                ("SMA", "Systèmes multi-agents", 1, 0, "ai"),
                ("AR", "Apprentissage par renforcement", 1, 0, "ai"),
                ("MR", "Méthodologie de recherche", 0, 0, "misc")],
    "M2-SECU": [("SAW", "Sécurité des applications web", 1, 1, "sec"),
                ("FOR", "Investigation numérique (forensique)", 1, 1, "sec"),
                ("PENT", "Tests d'intrusion", 0, 1, "sec"),
                ("SCL", "Sécurité du cloud", 1, 0, "sec"),
                ("MR", "Méthodologie de recherche", 0, 0, "misc")],
    "M2-GL":   [("DEVOPS", "DevOps et intégration continue", 1, 1, "prog"),
                ("MSV", "Architectures microservices", 1, 1, "prog"),
                ("IEX", "Ingénierie des exigences", 1, 0, "prog"),
                ("AGI", "Gestion de projets agiles", 1, 0, "misc"),
                ("MR", "Méthodologie de recherche", 0, 0, "misc")],
    "M2-DS":   [("BIG", "Big data", 1, 1, "data"),
                ("DL", "Deep learning", 1, 1, "ai"),
                ("ED", "Entrepôts de données", 1, 0, "data"),
                ("ST", "Séries temporelles", 1, 0, "math"),
                ("MR", "Méthodologie de recherche", 0, 0, "misc")],
    "M2-RES":  [("IOT", "Internet des objets", 1, 1, "net"),
                ("CLOUD", "Cloud computing", 1, 1, "sys"),
                ("SDN", "SDN et virtualisation des réseaux", 1, 1, "net"),
                ("SECR", "Sécurité des réseaux", 1, 0, "sec"),
                ("MR", "Méthodologie de recherche", 0, 0, "misc")],
}
THEMES = ["prog", "math", "sys", "data", "net", "ai", "sec"]   # + "misc" for anyone

SIZES = {
    "small": {
        # one common level + one L3 speciality + one master speciality
        "levels": {"L1-INFO": 90, "L3-ISIL": 60, "M1-IA": 28},
        "modules_per_level": 4,
        "rooms": [("Amphi 1", "amphi", 120),
                  ("Salle 1", "td", 40), ("Salle 2", "td", 40), ("Salle 3", "td", 32),
                  ("Salle A-1", "lab", 40), ("Salle TP1", "lab", 32)],
        "n_profs": 10, "n_vacataires": 3,
    },
    "real": {
        "levels": {"L1-INFO": 240, "L2-INFO": 200, "L3-ISIL": 90, "L3-SI": 70,
                   "M1-IA": 32, "M1-SECU": 28, "M1-GL": 30, "M1-DS": 30, "M1-RES": 25,
                   "M2-IA": 28, "M2-SECU": 25, "M2-GL": 27, "M2-DS": 26, "M2-RES": 22},
        "modules_per_level": None,  # all of them
        # (name, type, capacity): write the names your department uses
        "rooms": [("Amphi 1", "amphi", 250), ("Amphi 2", "amphi", 220), ("Amphi 3", "amphi", 150),
                  ("Salle 1", "td", 45), ("Salle 2", "td", 45), ("Salle 3", "td", 40),
                  ("Salle 4", "td", 40), ("Salle 5", "td", 40), ("Salle 6", "td", 40),
                  ("Salle 7", "td", 40), ("Salle 8", "td", 40), ("Salle 9", "td", 36),
                  ("Salle 10", "td", 36), ("Salle 11", "td", 32), ("Salle 12", "td", 32),
                  ("Salle 13", "td", 32), ("Salle 14", "td", 32), ("Salle 15", "td", 32),
                  ("Salle TP1", "lab", 40), ("Salle TP2", "lab", 40), ("Salle TP3", "lab", 40),
                  ("Salle TP4", "lab", 36), ("Salle TP5", "lab", 32),
                  ("Salle A-1", "lab", 40), ("Salle A-2", "lab", 40), ("Salle A-3", "lab", 36),
                  ("Salle B-1", "lab", 40), ("Salle B-2", "lab", 36), ("Salle B-3", "lab", 32)],
        "n_profs": 40, "n_vacataires": 10,
    },
}

RULES = {
    "session_minutes": 90,
    "section_max": 250,   # biggest section = biggest amphi (L1 = one section of 240)
    "group_size": 40,     # target group size (G1, G2...)
    "group_max": 40,      # a group never has more than 40 students
    "max_sessions_per_day_group": 4,
    "max_sessions_per_day_prof": 4,
    # allowed room types per kind of session (capacity must also fit the group).
    # Small master sections can have their lectures in a TD room.
    "room_types_for": {"lecture": ["amphi", "td"], "td": ["td"], "tp": ["lab"]},
}


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------
def make_department(size, seed, vary=False, week="sat"):
    rnd = random.Random(seed)
    cfg = SIZES[size]
    # --vary uses its OWN random generator, so without --vary the department
    # is exactly the same as before for a given seed.
    vr = random.Random(seed * 7919 + 1)
    changes = []          # human-readable list of what --vary changed

    DAYS = WEEKS[week]
    calendar = {"days": DAYS,
                "slots": [{"id": i, "start": s, "end": e} for i, (s, e) in enumerate(SLOTS)]}

    levels = []
    for lid, hc in cfg["levels"].items():
        year, spec, name = LEVELS[lid]
        if vary:                                   # +/- 20% students
            new_hc = max(15, round(hc * vr.uniform(0.8, 1.2)))
            if new_hc != hc:
                changes.append(f"{lid}: {hc} -> {new_hc} students")
            hc = new_hc
        levels.append({"id": lid, "year": year, "speciality": spec, "name": name,
                       "headcount": hc, "days": list(DAYS)})       # every level follows the study week

    rooms = []
    for name, rtype, cap in cfg["rooms"]:
        rooms.append({"id": name.replace(" ", "-"),      # "Salle A-2" -> "Salle-A-2"
                      "name": name, "type": rtype, "capacity": cap})
    if vary:                                       # close 0-2 TD rooms and 0-2 labs
        for rtype in ("td", "lab"):
            for _ in range(vr.randint(0, 2)):
                same = [r for r in rooms if r["type"] == rtype]
                big = [r for r in same if r["capacity"] >= RULES["group_max"]]
                # never close a room if fewer than 3 big ones (40+ seats) would remain
                cands = [r for r in same if r["capacity"] < RULES["group_max"] or len(big) > 3]
                if len(same) > 3 and cands:
                    closed = vr.choice(cands)
                    rooms.remove(closed)
                    changes.append(f"room closed: {closed['name']}")

    modules = []
    for lid in cfg["levels"]:
        chosen = MODULES[lid][: cfg["modules_per_level"]] if cfg["modules_per_level"] else MODULES[lid]
        for code, name, td, tp, theme in chosen:
            if vary:                               # sometimes drop or add a TD/TP
                r = vr.random()
                if r < 0.10 and td:
                    td = 0
                    changes.append(f"{lid}-{code}: no TD")
                elif r < 0.20 and tp:
                    tp = 0
                    changes.append(f"{lid}-{code}: no TP")
                elif r < 0.27 and not tp and theme != "misc":
                    tp = 1
                    changes.append(f"{lid}-{code}: TP added")
            modules.append({"id": f"{lid}-{code}", "name": name, "level": lid,
                            "theme": theme, "weekly": {"lecture": 1, "td": td, "tp": tp}})

    dept = {"meta": {"size": size, "seed": seed, "vary": vary, "changes": changes}, "calendar": calendar, "rules": RULES,
            "levels": levels, "rooms": rooms, "modules": modules,
            "professors": [], "unavailability": []}

    # ---- professors -------------------------------------------------------
    used_names = set()

    def new_name():
        while True:
            n = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
            if n not in used_names:
                used_names.add(n)
                return n

    profs = []
    n_perm, n_vac = cfg["n_profs"], cfg["n_vacataires"]
    if vary:                                       # a few professors more or fewer
        dp, dv = vr.randint(-4, 3), vr.randint(-3, 3)
        n_perm, n_vac = max(3, n_perm + dp), max(0, n_vac + dv)
        if dp or dv:
            changes.append(f"professors: {cfg['n_profs']}+{cfg['n_vacataires']} -> {n_perm}+{n_vac}")
    n_total = n_perm + n_vac
    for i in range(n_total):
        vac = i >= n_perm
        grade = "Vacataire" if vac else rnd.choice(["MCA", "MCB", "MAA", "Professeur"])
        themes = rnd.sample(THEMES, 2)  # a main + a secondary specialty
        profs.append({"id": f"P{i + 1:02d}", "name": new_name(), "grade": grade,
                      "max_hours": rnd.choice([6, 7.5, 9]) if vac else rnd.choice([9, 10.5, 12, 13.5, 15]),
                      "voeux": [], "_themes": themes, "_vac": vac})

    # vœux: each prof picks 3-5 modules in their themes; vacataires do TD/TP only
    for p in profs:
        main = [m for m in modules if m["theme"] == p["_themes"][0]]
        second = [m for m in modules if m["theme"] in (p["_themes"][1], "misc")]
        rnd.shuffle(main)
        rnd.shuffle(second)
        picks = (main[:3] + second)[: rnd.randint(3, 5)]
        for rank, m in enumerate(picks, 1):
            kinds = [k for k in ("lecture", "td", "tp") if m["weekly"][k]]
            if p["_vac"]:
                kinds = [k for k in kinds if k != "lecture"]
            if kinds:
                p["voeux"].append({"module": m["id"], "kinds": kinds, "rank": rank})

    groups = build_groups(dept)

    # with --vary, hire extra professors if the teaching load is too high (> 80%)
    if vary:
        hours = RULES["session_minutes"] / 60
        need = len(session_demand(dept, groups)) * hours
        added = 0
        while sum(p["max_hours"] for p in profs) * 0.8 < need:
            themes = rnd.sample(THEMES, 2)
            profs.append({"id": f"P{len(profs) + 1:02d}", "name": new_name(), "grade": "MAA",
                          "max_hours": 12, "voeux": [], "_themes": themes, "_vac": False})
            main = [m for m in modules if m["theme"] == themes[0]]
            rnd.shuffle(main)
            for rank, m in enumerate(main[:4], 1):
                kinds = [k for k in ("lecture", "td", "tp") if m["weekly"][k]]
                profs[-1]["voeux"].append({"module": m["id"], "kinds": kinds, "rank": rank})
            added += 1
        if added:
            changes.append(f"hired {added} extra professor(s) to cover the load")

    # make sure the professors can actually cover every session (greedy check)
    ensure_coverage(dept, profs, groups)

    for p in profs:
        del p["_themes"], p["_vac"]
    dept["professors"] = profs

    # ---- unavailability (blocked slots) ----------------------------------
    all_slots = [(d, s) for d in DAYS for s in range(len(SLOTS))]
    for p in profs:
        n = rnd.randint(6, 10) if p["grade"] == "Vacataire" else rnd.randint(2, 6)
        blocked = set(rnd.sample(all_slots, n))
        if rnd.random() < 0.3:  # sometimes a whole morning, e.g. "no Sunday mornings"
            d = rnd.choice(DAYS)
            blocked |= {(d, s) for s in (0, 1, 2)}
        if "Sat" in DAYS and rnd.random() < 0.5:  # half the professors never teach on Saturday
            blocked |= {("Sat", s) for s in range(len(SLOTS))}
        for d, s in sorted(blocked, key=lambda x: (DAYS.index(x[0]), x[1])):
            dept["unavailability"].append({"prof": p["id"], "day": d, "slot": s})

    # ---- dislikes (soft preferences: "I'd rather not") ---------------------
    # about 40% of professors dislike 1 or 2 things: 08:00, the last slot,
    # a whole day, or one slot on one day. The solver tries to respect them.
    for p in profs:
        p["dislikes"] = []
        if rnd.random() < 0.4:
            options = [{"day": "all", "slot": 0},
                       {"day": "all", "slot": len(SLOTS) - 1},
                       {"day": rnd.choice(DAYS), "slot": "all"},
                       {"day": rnd.choice(DAYS), "slot": rnd.randrange(len(SLOTS))}]
            p["dislikes"] = rnd.sample(options, rnd.randint(1, 2))

    return dept, groups


def ensure_coverage(dept, profs, groups):
    """Greedy assignment check. If a session cannot be covered, give the prof
    with the most spare hours an extra vœu for it. Guarantees a feasible
    professor assignment exists (timetabling feasibility is the solver's job)."""
    hours = dept["rules"]["session_minutes"] / 60
    demand = session_demand(dept, groups)

    def qualified(mod, kind):
        return [p for p in profs
                if any(v["module"] == mod and kind in v["kinds"] for v in p["voeux"])]

    left = {p["id"]: p["max_hours"] for p in profs}
    demand.sort(key=lambda d: len(qualified(d[0], d[1])))  # hardest first
    added = 0
    for mod, kind, _ in demand:
        cands = [p for p in qualified(mod, kind) if left[p["id"]] >= hours]
        if not cands:
            pool = [p for p in profs if left[p["id"]] >= hours
                    and not (kind == "lecture" and p["_vac"])]
            if not pool:
                raise RuntimeError("Not enough professor hours: raise n_profs or max_hours")
            # prefer someone whose specialty matches the module's theme
            theme = next(m["theme"] for m in dept["modules"] if m["id"] == mod)
            best = max(pool, key=lambda p: (theme in p["_themes"], left[p["id"]]))
            v = next((v for v in best["voeux"] if v["module"] == mod), None)
            if v:
                v["kinds"].append(kind)
            else:
                best["voeux"].append({"module": mod, "kinds": [kind], "rank": len(best["voeux"]) + 1})
            cands = [best]
            added += 1
        p = max(cands, key=lambda p: left[p["id"]])
        left[p["id"]] -= hours
    return added


# --------------------------------------------------------------------------
# Messy export (what a real department would upload)
# --------------------------------------------------------------------------
def write_messy(dept, folder, xlsx_path):
    os.makedirs(folder, exist_ok=True)
    mod_by_id = {m["id"]: m for m in dept["modules"]}
    lvl_by_id = {l["id"]: l for l in dept["levels"]}
    kind_fr = {"lecture": "Cours", "td": "TD", "tp": "TP"}
    rtype_fr = {"amphi": "Amphithéâtre", "td": "Salle TD", "lab": "Labo TP"}

    tables = {
        "niveaux": (["Année", "Spécialité", "Intitulé de la formation", "Effectif"],
                    [[l["year"], l["speciality"], l["name"], l["headcount"]] for l in dept["levels"]]),
        "salles": (["Salle", "Type de salle", "Capacité"],
                   [[r["name"], rtype_fr[r["type"]], r["capacity"]] for r in dept["rooms"]]),
        "modules": (["Intitulé du module", "Année", "Spécialité", "Cours/sem", "TD/sem", "TP/sem"],
                    [[m["name"], lvl_by_id[m["level"]]["year"], lvl_by_id[m["level"]]["speciality"],
                      m["weekly"]["lecture"], m["weekly"]["td"], m["weekly"]["tp"]]
                     for m in dept["modules"]]),
        "fiche_voeux": (["Nom & Prénom", "Grade", "Charge max (h/sem)", "Module souhaité",
                         "Formation", "Nature (Cours/TD/TP)", "Ordre de préférence"],
                        [[p["name"], p["grade"], p["max_hours"], mod_by_id[v["module"]]["name"],
                          mod_by_id[v["module"]]["level"],
                          "/".join(kind_fr[k] for k in v["kinds"]), v["rank"]]
                         for p in dept["professors"] for v in p["voeux"]]),
    }
    # availability as a grid: one row per prof x day, X = unavailable
    blocked = {(u["prof"], u["day"], u["slot"]) for u in dept["unavailability"]}
    slot_cols = [f"{s}-{e}" for s, e in SLOTS]
    tables["disponibilites"] = (
        ["Enseignant", "Jour"] + slot_cols,
        [[p["name"], DAYS_FR[d]] + ["X" if (p["id"], d, s) in blocked else "" for s in range(len(SLOTS))]
         for p in dept["professors"] for d in dept["calendar"]["days"]])
    slot_fr = {"all": "Toute la journée", **{i: c for i, c in enumerate(slot_cols)}}
    tables["preferences"] = (
        ["Enseignant", "Jour à éviter", "Créneau à éviter"],
        [[p["name"], "Tous les jours" if d["day"] == "all" else DAYS_FR[d["day"]], slot_fr[d["slot"]]]
         for p in dept["professors"] for d in p.get("dislikes", [])])

    for name, (header, rows) in tables.items():
        with open(os.path.join(folder, f"{name}.csv"), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")  # ';' is what French Excel uses
            w.writerow(header)
            w.writerows(rows)

    truth = {
        "niveaux.csv": {"Année": "level.year", "Spécialité": "level.speciality",
                        "Intitulé de la formation": "level.name", "Effectif": "level.headcount"},
        "salles.csv": {"Salle": "room.name", "Type de salle": "room.type",
                       "Capacité": "room.capacity"},
        "modules.csv": {"Intitulé du module": "module.name", "Année": "module.year",
                        "Spécialité": "module.speciality",
                        "Cours/sem": "module.weekly.lecture", "TD/sem": "module.weekly.td",
                        "TP/sem": "module.weekly.tp"},
        "fiche_voeux.csv": {"Nom & Prénom": "professor.name", "Grade": "professor.grade",
                            "Charge max (h/sem)": "professor.max_hours",
                            "Module souhaité": "voeu.module", "Formation": "voeu.level",
                            "Nature (Cours/TD/TP)": "voeu.kinds",
                            "Ordre de préférence": "voeu.rank"},
        "preferences.csv": {"Enseignant": "dislike.prof", "Jour à éviter": "dislike.day",
                            "Créneau à éviter": "dislike.slot"},
        "disponibilites.csv": {"Enseignant": "availability.prof", "Jour": "availability.day",
                               **{c: f"availability.slot.{i}" for i, c in enumerate(slot_cols)}},
    }
    with open(os.path.join(folder, "columns_truth.json"), "w", encoding="utf-8") as f:
        json.dump(truth, f, ensure_ascii=False, indent=2)

    try:
        from openpyxl import Workbook
        wb = Workbook()
        wb.remove(wb.active)
        for name, (header, rows) in tables.items():
            ws = wb.create_sheet(name)
            ws.append(header)
            for r in rows:
                ws.append(r)
        wb.save(xlsx_path)
    except ImportError:
        print("  (openpyxl not installed: skipped the .xlsx file)")


# --------------------------------------------------------------------------
def print_stats(dept, groups):
    demand = session_demand(dept, groups)
    n_slots = len(dept["calendar"]["days"]) * len(SLOTS)
    hours = dept["rules"]["session_minutes"] / 60
    by_id = {g["id"]: g for g in groups}
    rooms = dept["rooms"]
    print(f"  levels: {len(dept['levels'])}, modules: {len(dept['modules'])}, "
          f"profs: {len(dept['professors'])}, rooms: {len(rooms)}")
    kinds = defaultdict(int)
    for g in groups:
        kinds[g["kind"]] += 1
    print(f"  groups: {kinds['section']} sections, {kinds['group']} groups")
    print(f"  sessions to place per week: {len(demand)}")

    max_td_room = max(r["capacity"] for r in rooms if r["type"] == "td")
    big_lect = sum(1 for _, k, g in demand if k == "lecture" and by_id[g]["size"] > max_td_room)
    n_amphi = sum(r["type"] == "amphi" for r in rooms) * n_slots
    print(f"    big lectures (need an amphi) {big_lect:4d} / {n_amphi:4d} amphi-slots "
          f"({100 * big_lect / n_amphi:.0f}%)")
    rest = sum(1 for d in demand if d[1] != "tp") - big_lect
    cap = sum(r["type"] in ("amphi", "td") for r in rooms) * n_slots - big_lect
    print(f"    other lectures + TD       {rest:4d} / {cap:4d} room-slots ({100 * rest / cap:.0f}%)")
    tp = sum(d[1] == "tp" for d in demand)
    labs = sum(r["type"] == "lab" for r in rooms) * n_slots
    print(f"    TP                        {tp:4d} / {labs:4d} lab-slots  ({100 * tp / labs:.0f}%)")

    total_h = len(demand) * hours
    prof_h = sum(p["max_hours"] for p in dept["professors"])
    print(f"  teaching load {total_h:.0f} h / prof capacity {prof_h:.0f} h ({100 * total_h / prof_h:.0f}%)")
    per_group = defaultdict(int)
    for _, _, gid in demand:
        per_group[gid] += 1
    worst = max(sum(per_group[a] for a in chain(g, by_id)) for g in groups if g["kind"] == "group")
    print(f"  busiest student group: {worst} sessions / {n_slots} slots per week")


def chain(g, by_id):
    out = [g["id"]]
    while g["parent"]:
        g = by_id[g["parent"]]
        out.append(g["id"])
    return out


def main():
    ap = argparse.ArgumentParser(description="Generate a synthetic department")
    ap.add_argument("--size", choices=SIZES, default="real")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="out")
    ap.add_argument("--week", choices=WEEKS, default="sat",
                    help="study week chosen by the admin: sat = Saturday-Thursday, sun = Sunday-Thursday")
    ap.add_argument("--vary", action="store_true",
                    help="also randomise headcounts, rooms, TD/TP and number of professors")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    dept, groups = make_department(args.size, args.seed, vary=args.vary, week=args.week)
    with open(os.path.join(args.out, f"department_{args.size}.json"), "w", encoding="utf-8") as f:
        json.dump(dept, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, f"groups_{args.size}.json"), "w", encoding="utf-8") as f:
        json.dump(groups, f, ensure_ascii=False, indent=2)
    write_messy(dept, os.path.join(args.out, f"messy_{args.size}"),
                os.path.join(args.out, f"messy_{args.size}.xlsx"))
    print(f"Wrote {args.out}/ (size={args.size}, seed={args.seed}, week={args.week}{', varied' if args.vary else ''})")
    if args.vary:
        print(f"  {len(dept['meta']['changes'])} changes from the base department:")
        for c in dept["meta"]["changes"]:
            print("   -", c)
    print_stats(dept, groups)


if __name__ == "__main__":
    main()
