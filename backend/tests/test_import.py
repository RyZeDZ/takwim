import io
import json

from openpyxl import Workbook


def xlsx(rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def pdf_table(rows) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    t = Table(rows)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, "black")]))
    doc.build([t])
    return buf.getvalue()


def preview(client, admin, kind, filename, content, overrides=None):
    data = {"kind": kind}
    if overrides:
        data["column_overrides"] = json.dumps(overrides)
    return client.post("/admin/import/preview", headers=admin, data=data,
                       files={"file": (filename, content)})


def test_full_import_pipeline(client, admin):
    # 1. Levels from a CSV with ';' and French headers
    csv_bytes = "Promotion;Effectif;Remarque\nL1 Informatique;160;\nL3 ISIL;70;ok\n".encode()
    r = preview(client, admin, "levels", "niveaux.csv", csv_bytes)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["mapping"]["name"]["column"] == "Promotion"
    assert p["mapping"]["headcount"]["column"] == "Effectif"
    assert p["unmapped_columns"] == ["Remarque"] and p["ready"]
    assert p["rows"] == [{"name": "L1 Informatique", "headcount": 160},
                         {"name": "L3 ISIL", "headcount": 70}]
    c = client.post("/admin/import/commit", headers=admin, json={"kind": "levels", "rows": p["rows"]})
    assert c.json()["created"] == 2

    # 2. Rooms from a messy Excel file (title line, odd headers, types written in words)
    content = xlsx([
        ["Faculté des sciences - liste des salles"],
        [],
        ["N°", "Désignation", "Nature", "Nombre de places"],
        [1, "Amphi A", "Amphithéâtre", 220],
        [2, "Salle 12", "Salle de TD", "40 places"],
        [3, "Labo 3", "Salle TP machines", 20],
        [None, None, None, None],
    ])
    p = preview(client, admin, "rooms", "salles.xlsx", content).json()
    assert p["mapping"]["name"]["column"] == "Désignation"
    assert p["mapping"]["capacity"]["column"] == "Nombre de places"
    assert [r["type"] for r in p["rows"]] == ["amphi", "td", "lab"]
    assert [r["capacity"] for r in p["rows"]] == [220, 40, 20]
    client.post("/admin/import/commit", headers=admin, json={"kind": "rooms", "rows": p["rows"]})

    # 3. Modules from a PDF (exported from Word), hours written as '3h00'
    content = pdf_table([
        ["Niveau", "Intitulé du module", "Cours", "TD", "TP"],
        ["L1 Informatique", "Algorithmique 1", "3h00", "3h00", "1h30"],
        ["L3 ISIL", "Compilation", "1", "1", "1"],
        ["M2 Inconnu", "Fantôme", "1", "0", "0"],
    ])
    p = preview(client, admin, "modules", "modules.pdf", content).json()
    assert p["mapping"]["name"]["column"] == "Intitulé du module"
    algo = p["rows"][0]
    assert (algo["lecture"], algo["td"], algo["tp"]) == (2, 2, 1)
    c = client.post("/admin/import/commit", headers=admin, json={"kind": "modules", "rows": p["rows"]}).json()
    assert c["created"] == 2 and c["skipped"] == 1 and "M2 Inconnu" in c["warnings"][0]

    # 4. Professors with separate Nom / Prénom and a list of modules
    csv_bytes = ("Nom,Prénom,Modules enseignés,Charge\n"
                 "Kaci,Amel,Algorithmique 1; Compilation,10\n"
                 "Touati,Omar,Module qui n'existe pas,\n").encode()
    p = preview(client, admin, "professors", "profs.csv", csv_bytes).json()
    assert p["rows"][0]["name"] == "Amel Kaci"
    assert p["rows"][0]["modules"] == ["Algorithmique 1", "Compilation"]
    assert p["rows"][0]["max_sessions"] == 10 and p["rows"][1]["max_sessions"] is None
    c = client.post("/admin/import/commit", headers=admin, json={"kind": "professors", "rows": p["rows"]}).json()
    assert c["created"] == 2 and len(c["credentials"]) == 2
    assert any("n'existe pas" in w for w in c["warnings"])
    profs = client.get("/admin/professors", headers=admin).json()
    amel = next(x for x in profs if x["name"] == "Amel Kaci")
    assert len(amel["teaches"]) == 2
    omar = next(x for x in profs if x["name"] == "Omar Touati")
    assert omar["max_sessions"] == 12  # empty cell -> the department's default load

    # Re-importing updates instead of duplicating
    c = client.post("/admin/import/commit", headers=admin, json={"kind": "professors", "rows": p["rows"]}).json()
    assert c["created"] == 0 and c["updated"] == 2


def test_import_errors_and_overrides(client, admin):
    assert preview(client, admin, "rooms", "x.docx", b"hello").status_code == 422
    assert preview(client, admin, "spaceships", "x.csv", b"a,b\n1,2").status_code == 422
    assert preview(client, admin, "rooms", "x.xlsx", b"not really excel").status_code == 422
    # Headers nobody could guess: the admin points at the right columns
    csv_bytes = "Col A,Col B\nSalle 7,35\n".encode()
    p = preview(client, admin, "rooms", "x.csv", csv_bytes).json()
    assert not p["ready"] and "capacity" in p["missing_required"]
    p = preview(client, admin, "rooms", "x.csv", csv_bytes,
                overrides={"name": "Col A", "capacity": "Col B"}).json()
    assert p["ready"] and p["rows"] == [{"name": "Salle 7", "type": "td", "capacity": 35}]
    assert p["mapping"]["capacity"]["method"] == "admin"
    kinds = client.get("/admin/import/kinds", headers=admin).json()
    assert set(kinds) == {"rooms", "levels", "modules", "professors"}
