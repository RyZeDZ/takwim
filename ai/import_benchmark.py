"""How well are messy column headers recognised? Dictionary alone vs dictionary + local LLM.

10 header sets written the way department files are (French, English, abbreviations,
extra columns), with the correct answer for each. Run from the backend folder:

    cd backend && .venv/bin/python ../ai/import_benchmark.py

A field counts as right when it is matched to the correct column, wrong when it is matched
to another column (worse than missing: the admin has to notice it), missing otherwise.
"""
import os
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from app.importers.mapping import map_columns  # noqa: E402

CASES = [
    ("rooms", ["N°", "Désignation du local", "Nature", "Nbre de places assises"],
     {"name": "Désignation du local", "type": "Nature", "capacity": "Nbre de places assises"}),
    ("rooms", ["Code", "Bloc", "Cap. accueil", "Usage"],
     {"name": "Code", "capacity": "Cap. accueil", "type": "Usage"}),
    ("rooms", ["Room ID", "Seats", "Category"],
     {"name": "Room ID", "capacity": "Seats", "type": "Category"}),
    ("levels", ["Promo", "Nb inscrits", "Observations"],
     {"name": "Promo", "headcount": "Nb inscrits"}),
    ("levels", ["Année d'étude", "Filière", "Intitulé", "Inscrits 2026"],
     {"year": "Année d'étude", "speciality": "Filière", "name": "Intitulé", "headcount": "Inscrits 2026"}),
    ("modules", ["Matière", "Niveau", "VH Cours", "VH TD", "VH TP"],
     {"name": "Matière", "level": "Niveau", "lecture": "VH Cours", "td": "VH TD", "tp": "VH TP"}),
    ("modules", ["Unité d'enseignement", "Parcours", "CM", "TD", "TP", "Coef"],
     {"name": "Unité d'enseignement", "level": "Parcours", "lecture": "CM", "td": "TD", "tp": "TP"}),
    ("modules", ["Course title", "Programme", "Lectures/wk", "Tutorials/wk", "Labs/wk"],
     {"name": "Course title", "level": "Programme", "lecture": "Lectures/wk", "td": "Tutorials/wk", "tp": "Labs/wk"}),
    ("professors", ["Enseignant(e)", "Grade", "Volume horaire max", "Matières souhaitées", "Nature"],
     {"name": "Enseignant(e)", "max_sessions": "Volume horaire max", "modules": "Matières souhaitées", "kinds": "Nature"}),
    ("professors", ["Nom complet", "Charge hebdo", "Vœu", "Priorité", "Type (C/TD/TP)", "Promotion"],
     {"name": "Nom complet", "max_sessions": "Charge hebdo", "modules": "Vœu", "rank": "Priorité",
      "kinds": "Type (C/TD/TP)", "level": "Promotion"}),
]


def score(use_llm: bool):
    os.environ["COLUMN_MAPPER_MODULE"] = "ai.column_mapper" if use_llm else ""
    right = wrong = missing = 0
    t0 = time.perf_counter()
    for kind, headers, truth in CASES:
        mapping = map_columns(kind, headers)["mapping"]
        for field, header in truth.items():
            got = mapping.get(field, {}).get("column")
            if got == header:
                right += 1
            elif got:
                wrong += 1
                print(f"   wrong   {kind}.{field}: '{got}' instead of '{header}'")
            else:
                missing += 1
                print(f"   missing {kind}.{field} ('{header}')")
    return right, wrong, missing, time.perf_counter() - t0


if __name__ == "__main__":
    total = sum(len(t) for _, _, t in CASES)
    for label, llm in (("dictionary only", False), ("dictionary + local LLM", True)):
        print(f"\n{label}:")
        r, w, m, s = score(llm)
        print(f"=> {r}/{total} fields right ({100 * r / total:.0f}%), {w} wrong, {m} missing, "
              f"{s:.1f} s for {len(CASES)} files")
    print(f"\npeak memory of this process: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB")
