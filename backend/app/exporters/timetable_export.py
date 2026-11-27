"""Export timetables as Excel (one sheet per group) or PDF (one page per group).

Layout = what departments already print: days as rows, time slots as columns,
each cell 'Module (TD) / Professor / Room'.
"""
import io
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session as DB

from ..models import Professor, Room, Session
from ..rules import get_rules
from ..services.groups import GroupTree

KIND_LABEL = {"lecture": "Lecture", "td": "TD", "tp": "TP"}


def _grids(db: DB, scope: str, ids: list[int] | None) -> list[tuple[str, dict]]:
    """Returns [(title, {(day, slot): [cell text]})]."""
    tree = GroupTree.load(db)
    sessions = list(db.scalars(select(Session)))
    out = []
    if scope == "group":
        groups = [g for g in tree.by_id.values() if (ids is None and not tree.children[g.id])
                  or (ids is not None and g.id in ids)]
        groups.sort(key=lambda g: g.name)
        for g in groups:
            chain = {g.id, *tree.ancestors(g.id)}
            grid = defaultdict(list)
            for s in sessions:
                if s.group_id in chain:
                    grid[(s.day, s.slot)].append(
                        f"{s.module.name} ({KIND_LABEL.get(s.kind, s.kind)})\n{s.professor.name}\n{s.room.name}")
            out.append((g.name, grid))
    elif scope == "prof":
        profs = db.scalars(select(Professor).order_by(Professor.name))
        for p in profs:
            if ids is not None and p.id not in ids:
                continue
            grid = defaultdict(list)
            for s in sessions:
                if s.professor_id == p.id:
                    grid[(s.day, s.slot)].append(
                        f"{s.module.name} ({KIND_LABEL.get(s.kind, s.kind)})\n{s.group.name}\n{s.room.name}")
            out.append((p.name, grid))
    elif scope == "room":
        for r in db.scalars(select(Room).order_by(Room.name)):
            if ids is not None and r.id not in ids:
                continue
            grid = defaultdict(list)
            for s in sessions:
                if s.room_id == r.id:
                    grid[(s.day, s.slot)].append(
                        f"{s.module.name} ({KIND_LABEL.get(s.kind, s.kind)})\n{s.group.name}\n{s.professor.name}")
            out.append((r.name, grid))
    else:
        raise ValueError("scope must be group, prof or room")
    return out


def to_excel(db: DB, scope: str = "group", ids: list[int] | None = None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = Workbook()
    wb.remove(wb.active)
    thin = Side(style="thin", color="999999")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor="DDE7F5")
    used = set()
    rules = get_rules(db)
    for title, grid in _grids(db, scope, ids) or [("Empty", {})]:
        name = "".join(c for c in title if c not in '[]:*?/\\')[:31] or "Sheet"
        base, n = name, 1
        while name in used:
            n += 1
            name = f"{base[:28]}-{n}"
        used.add(name)
        ws = wb.create_sheet(name)
        ws.cell(1, 1, f"Timetable: {title}").font = Font(bold=True, size=13)
        ws.cell(2, 1, "Day / Time").font = Font(bold=True)
        for j, label in enumerate(rules.time_slots, start=2):
            c = ws.cell(2, j, label)
            c.font, c.fill, c.border = Font(bold=True), head_fill, border
            c.alignment = Alignment(horizontal="center")
            ws.column_dimensions[c.column_letter].width = 26
        ws.column_dimensions["A"].width = 13
        for i, day in enumerate(rules.day_names):
            row = i + 3
            c = ws.cell(row, 1, day)
            c.font, c.fill, c.border = Font(bold=True), head_fill, border
            ws.row_dimensions[row].height = 62
            for s in range(rules.n_slots):
                cell = ws.cell(row, s + 2, "\n---\n".join(grid.get((i, s), [])))
                cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
                cell.border = border
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_pdf(db: DB, scope: str = "group", ids: list[int] | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=20, rightMargin=20,
                            topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("cell", fontSize=7.5, leading=9, alignment=1)
    story = []
    rules = get_rules(db)
    pages = _grids(db, scope, ids) or [("Empty", {})]
    for k, (title, grid) in enumerate(pages):
        story.append(Paragraph(f"Timetable: {title}", styles["Title"]))
        data = [["Day"] + rules.time_slots]
        for i, day in enumerate(rules.day_names):
            row = [day]
            for s in range(rules.n_slots):
                text = "<br/>---<br/>".join(t.replace("\n", "<br/>") for t in grid.get((i, s), []))
                row.append(Paragraph(text, cell_style))
            data.append(row)
        width = (landscape(A4)[0] - 40 - 70) / rules.n_slots
        table = Table(data, colWidths=[70] + [width] * rules.n_slots,
                      rowHeights=[20] + [70] * rules.n_days)
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE7F5")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#DDE7F5")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        story.append(table)
        if k < len(pages) - 1:
            story.append(PageBreak())
    doc.build(story)
    return buf.getvalue()
