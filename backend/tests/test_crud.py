from conftest import login_prof


def test_rooms_levels_modules(client, admin):
    assert client.get("/admin/rooms").status_code == 401
    r = client.post("/admin/rooms", json={"name": "Salle 1", "type": "td", "capacity": 40}, headers=admin)
    assert r.status_code == 201
    room = r.json()
    assert client.post("/admin/rooms", json={"name": "Salle 1", "type": "td", "capacity": 40},
                       headers=admin).status_code == 409
    assert client.post("/admin/rooms", json={"name": "X", "type": "kitchen", "capacity": 40},
                       headers=admin).status_code == 422
    r = client.patch(f"/admin/rooms/{room['id']}", json={"active": False}, headers=admin)
    assert r.json()["active"] is False
    assert len(client.get("/admin/rooms", headers=admin).json()) == 1
    assert client.delete(f"/admin/rooms/{room['id']}", headers=admin).status_code == 200
    assert client.get("/admin/rooms", headers=admin).json() == []

    lv = client.post("/admin/levels", json={"name": "L2", "headcount": 90}, headers=admin).json()
    m = client.post("/admin/modules", headers=admin, json={
        "level_id": lv["id"], "name": "Réseaux", "lecture_per_week": 1, "td_per_week": 1,
        "tp_per_week": 1}).json()
    assert client.post("/admin/modules", headers=admin, json={"level_id": 999, "name": "x"}).status_code == 404
    assert client.get(f"/admin/modules?level_id={lv['id']}", headers=admin).json()[0]["name"] == "Réseaux"
    upd = client.patch(f"/admin/modules/{m['id']}", headers=admin, json={
        "level_id": lv["id"], "name": "Réseaux 1", "lecture_per_week": 2}).json()
    assert upd["name"] == "Réseaux 1" and upd["lecture_per_week"] == 2


def test_professor_accounts(client, admin):
    lv = client.post("/admin/levels", json={"name": "L1", "headcount": 30}, headers=admin).json()
    mod = client.post("/admin/modules", json={"level_id": lv["id"], "name": "Algo"}, headers=admin).json()
    p = client.post("/admin/professors", headers=admin, json={
        "name": "Amel Kaci", "max_sessions": 10,
        "teaches": [{"module_id": mod["id"], "kinds": ["lecture", "td"]}]}).json()
    assert p["username"] == "amel.kaci" and p["password"]
    assert p["teaches"] == [{"module_id": mod["id"], "kinds": ["lecture", "td"], "rank": 1}]
    assert client.post("/admin/professors", headers=admin, json={"name": "Amel Kaci"}).status_code == 409
    prof = login_prof(client, p)
    assert client.get("/admin/rooms", headers=prof).status_code == 403  # profs aren't admins
    reset = client.post(f"/admin/professors/{p['id']}/reset-password", headers=admin).json()
    assert login_prof(client, reset)
    # Admin fills the availability grid for a professor
    r = client.put(f"/admin/professors/{p['id']}/availability", headers=admin,
                   json={"unavailable": [{"day": 0, "slot": s} for s in range(6)]})
    assert len(r.json()["unavailable"]) == 6
    assert client.get("/admin/professors", headers=admin).json()[0]["availability_filled"] is True
    assert client.put(f"/admin/professors/{p['id']}/availability", headers=admin,
                      json={"unavailable": [{"day": 9, "slot": 0}]}).status_code == 422
