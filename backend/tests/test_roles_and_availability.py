from conftest import login_prof


def test_roles(client, admin, demo):
    prof = login_prof(client, demo["credentials"][0])
    assert client.get("/admin/rooms", headers=prof).status_code == 403
    assert client.get("/me/timetable", headers=admin).status_code == 403
    assert client.get("/me/timetable").status_code == 401
    assert client.get("/me/timetable", headers=prof).status_code == 200
    assert client.get("/public/groups").status_code == 200  # students: no login


def test_availability_grid(client, admin, demo):
    prof = login_prof(client, demo["credentials"][0])
    body = {"unavailable": [{"day": 1, "slot": 0}, {"day": 1, "slot": 1}, {"day": 1, "slot": 1}]}
    r = client.put("/me/availability", json=body, headers=prof)
    assert r.status_code == 200 and len(r.json()["unavailable"]) == 2  # duplicates removed
    assert len(client.get("/me/availability", headers=prof).json()["unavailable"]) == 2
    assert client.put("/me/availability", json={"unavailable": [{"day": 9, "slot": 0}]},
                      headers=prof).status_code == 422


def test_group_tree(client, demo):
    tree = client.get("/public/groups").json()
    l1 = next(x for x in tree if x["level"] == "L1 CS")
    tds = l1["sections"][0]["children"]
    assert len(tds) == 6 and all(len(t["children"]) == 2 for t in tds)
