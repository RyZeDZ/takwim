"""Write the synthetic demo department as the files a department would really send:
French headers, a title line, the level split into year + speciality, one wish per row in the
professors' wish lists (fiche de voeux), loads in hours, and a mix of Excel, CSV and PDF.

    cd backend && .venv/bin/python scripts/make_demo_files.py      # -> ../data/demo-files/

Import them in the numbered order from the admin's "Import files" page. Everything is
synthetic (invented names), generated from app/demo_data.py.
"""
import csv
import io
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/files.db"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Font, PatternFill  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import getSampleStyleSheet  # noqa: E402
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.demo_data import seed_demo  # noqa: E402
from app.models import Level, Module, Professor, Room, Teaching  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "data" / "demo-files"
SCHOOL = "Département d'Informatique - Année universitaire 2026/2027"
ROOM_FR = {"amphi": "Amphithéâtre", "td": "Salle TD", "lab": "Salle machines (TP)"}
KIND_FR = {"lecture": "Cours", "td": "TD", "tp": "TP"}


def split_level(name: str) -> tuple[str, str]:
    year, _, spec = name.partition(" ")
    return year, spec


def excel(path: Path, title: str, header: list[str], rows: list[list]):
    wb = Workbook()
    ws = wb.active
    ws.title = "Feuil1"
    ws.append([SCHOOL])
    ws.append([title])
    ws.append([])
    ws.append(header)
    for c in ws[4]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="D8E4FA")
    for r in rows:
        ws.append(r)
    for col in ws.columns:
        ws.column_dimensions[col[3].column_letter].width = max(12, max(len(str(c.value or "")) for c in col[3:]) + 2)
    ws["A1"].font = Font(bold=True, size=13)
    wb.save(path)


def csv_file(path: Path, header: list[str], rows: list[list]):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")  # what French Excel writes
        w.writerow(header)
        w.writerows(rows)


def pdf(path: Path, title: str, header: list[str], rows: list[list]):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=title)
    styles = getSampleStyleSheet()
    table = Table([header] + [[str(c) for c in r] for r in rows], repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D8E4FA")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    doc.build([Paragraph(SCHOOL, styles["Normal"]), Paragraph(title, styles["Title"]), Spacer(1, 8), table])
    path.write_bytes(buf.getvalue())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    init_db()
    with SessionLocal() as db:
        seed_demo(db)
        levels = list(db.scalars(select(Level).order_by(Level.id)))
        level_of = {lv.id: lv for lv in levels}
        rooms = list(db.scalars(select(Room).order_by(Room.id)))
        modules = list(db.scalars(select(Module).order_by(Module.level_id, Module.id)))
        module_of = {m.id: m for m in modules}
        profs = list(db.scalars(select(Professor).order_by(Professor.name)))
        wishes = defaultdict(list)
        for t in db.scalars(select(Teaching).order_by(Teaching.rank)):
            wishes[t.professor_id].append(t)

    # 1. Levels (Excel): year and speciality in two columns, plus the long name.
    long = {"CS": "Informatique (tronc commun)", "ISIL": "Ingénierie des SI et du Logiciel",
            "SI": "Systèmes Informatiques", "AI": "Intelligence Artificielle", "SEC": "Cybersécurité"}
    excel(OUT / "1_niveaux.xlsx", "Effectifs par niveau",
          ["Année", "Spécialité", "Intitulé de la formation", "Effectif"],
          [[*split_level(lv.name), f"{split_level(lv.name)[0]} {long.get(split_level(lv.name)[1], '')}".strip(),
            lv.headcount] for lv in levels])

    # 2. Rooms (CSV, as exported from French Excel), with an extra column to ignore.
    csv_file(OUT / "2_salles.csv", ["Salle", "Bloc", "Type de salle", "Capacité"],
             [[r.name, "A" if r.type == "amphi" else ("C" if r.type == "lab" else "B"),
               ROOM_FR[r.type], r.capacity] for r in rooms])

    # 2bis. A second rooms file with unusual headers: shows the local language model at work.
    csv_file(OUT / "2bis_salles_bloc_D_entetes_inhabituels.csv", ["Code", "Bloc", "Cap. accueil", "Usage"],
             [["D-01", "Bloc D", 40, "Salle TD"], ["D-02", "Bloc D", 40, "Salle TD"],
              ["D-Labo", "Bloc D", 30, "Salle machines (TP)"]])

    # 3. Modules (PDF table, as printed from the official programme).
    pdf(OUT / "3_modules.pdf", "Volume horaire hebdomadaire des modules",
        ["Intitulé du module", "Année", "Spécialité", "Cours/sem", "TD/sem", "TP/sem"],
        [[m.name, *split_level(level_of[m.level_id].name), m.lecture_per_week, m.td_per_week, m.tp_per_week]
         for m in modules])

    # 4. Professors' wish lists (Excel): one wish per row, order of preference, load in hours.
    rows = []
    for p in profs:
        for t in wishes[p.id]:
            m = module_of[t.module_id]
            year, spec = split_level(level_of[m.level_id].name)
            rows.append([p.name, "MCB" if p.id % 3 else "MAA", round(p.max_sessions * 1.5), m.name,
                         f"{year}-{spec}", "/".join(KIND_FR[k] for k in t.kinds.split(",") if k), t.rank])
    excel(OUT / "4_fiche_de_voeux.xlsx", "Fiches de vœux des enseignants",
          ["Nom & Prénom", "Grade", "Charge max (h/sem)", "Module souhaité", "Formation",
           "Nature (Cours/TD/TP)", "Ordre de préférence"], rows)

    print(f"Written to {OUT}:")
    for f in sorted(OUT.iterdir()):
        print(f"  {f.name}  ({f.stat().st_size // 1024 or 1} KB)")


if __name__ == "__main__":
    main()
