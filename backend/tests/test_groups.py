def test_groups_are_built_from_headcounts(client, admin):
    assert client.post("/admin/demo/seed", headers=admin).status_code == 200
    r = client.post("/admin/groups/build", headers=admin).json()
    assert len(r["rebuilt"]) == 8
    levels = r["levels"]
    l1 = next(x for x in levels if x["level"] == "L1 CS")
    section = l1["sections"][0]
    assert section["size"] == 160
    tds = section["td"]
    assert len(tds) == 6 and sum(t["size"] for t in tds) == 160          # 6 TD groups of ~27
    assert all(t["tp"] == [] for t in tds)  # the TD group does the TP itself (default)
    m2 = next(x for x in levels if x["level"] == "M2 AI")
    assert m2["sections"][0]["td"][0]["size"] == 30


def test_stats_and_logs(client, admin):
    client.post("/admin/demo/seed", headers=admin)
    stats = client.get("/admin/stats", headers=admin).json()
    assert stats["levels"] == 8 and stats["rooms_active"] == 21 and stats["professors"] >= 15
    assert stats["sessions_per_week"] == 0
    actions = [x["action"] for x in client.get("/admin/logs", headers=admin).json()]
    assert "demo_seed" in actions


def test_groups_rebuild_only_what_changed(client, admin):
    client.post("/admin/demo/seed", headers=admin)
    client.post("/admin/groups/build", headers=admin)
    assert client.post("/admin/groups/build", headers=admin).json()["rebuilt"] == []
    lv = next(x for x in client.get("/admin/levels", headers=admin).json() if x["name"] == "M1 AI")
    client.patch(f"/admin/levels/{lv['id']}", headers=admin, json={"name": "M1 AI", "headcount": 70})
    assert client.post("/admin/groups/build", headers=admin).json()["rebuilt"] == ["M1 AI"]
    assert len(client.post("/admin/groups/build?force=true", headers=admin).json()["rebuilt"]) == 8


def test_demo_data_never_overwrites_real_data(client, admin, monkeypatch):
    client.post("/admin/rooms", headers=admin, json={"name": "Real room", "type": "td", "capacity": 30})
    r = client.post("/admin/demo/seed", headers=admin)
    assert r.status_code == 409
    assert [x["name"] for x in client.get("/admin/rooms", headers=admin).json()] == ["Real room"]
    from app.config import settings

    monkeypatch.setattr(settings, "demo_mode", False)
    assert client.post("/admin/demo/seed", headers=admin).status_code == 403


def test_tp_subgroups_when_the_department_splits(client, admin):
    client.post("/admin/demo/seed", headers=admin)
    client.post("/admin/groups/build", headers=admin)
    r = client.put("/admin/settings", headers=admin, json={"split_tp_groups": True})
    assert r.status_code == 200 and r.json()["changed"] == ["split_tp_groups"]
    assert client.put("/admin/settings", headers=admin, json={"split_tp_groups": "yes"}).status_code == 422
    levels = client.post("/admin/groups/build", headers=admin).json()["levels"]
    tds = next(x for x in levels if x["level"] == "L1 CS")["sections"][0]["td"]
    assert all(len(t["tp"]) == 2 for t in tds)                            # 2 TP subgroups each
    assert all(sum(tp["size"] for tp in t["tp"]) == t["size"] for t in tds)
    # The demo professors were sized for unsplit groups: some TP can't be staffed, and the
    # summary says which, but nothing invalid is ever saved.
    r = client.post("/admin/timetable/generate", headers=admin).json()
    assert r["saved"] and r["conflicts"] == []
    assert all(u["kind"] == "tp" for u in r["unscheduled"])
