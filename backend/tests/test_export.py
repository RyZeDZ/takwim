from io import BytesIO

from openpyxl import load_workbook


def test_exports(client, admin, demo):
    r = client.get("/export/excel")
    assert r.status_code == 200
    wb = load_workbook(BytesIO(r.content))
    assert len(wb.sheetnames) > 20  # one sheet per student group
    first = wb.worksheets[0]
    assert first["A3"].value == "Sunday" and first["B2"].value == "08:00-09:30"
    assert any(c.value for row in first.iter_rows(min_row=3) for c in row[1:])
    r = client.get("/export/pdf?scope=prof")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert client.get("/export/excel?scope=spaceship").status_code == 422


def test_closed_room_export_is_empty(client, admin, demo):
    salle = next(r for r in client.get("/admin/rooms", headers=admin).json() if r["name"] == "Room 12")
    client.patch(f"/admin/rooms/{salle['id']}", json={"active": False}, headers=admin)
    client.post("/admin/timetable/generate", headers=admin)
    wb = load_workbook(BytesIO(client.get(f"/export/excel?scope=room&ids={salle['id']}").content))
    assert len(wb.sheetnames) == 1
    cells = [c.value for row in wb.worksheets[0].iter_rows(min_row=3) for c in row[1:]]
    assert not any(cells)
