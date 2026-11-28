"""Professor preferences: wish-list order (rank), 'rather not' slots, and the daily limit."""
from collections import Counter

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Session
from conftest import login_prof


def test_avoid_slots_are_stored_apart_from_unavailable(client, admin, demo):
    prof = login_prof(client, demo["credentials"][0])
    body = {"unavailable": [{"day": 0, "slot": 0}],
            "avoid": [{"day": 0, "slot": 0}, {"day": 1, "slot": 5}]}
    r = client.put("/me/availability", json=body, headers=prof).json()
    assert r["unavailable"] == [{"day": 0, "slot": 0}]
    assert r["avoid"] == [{"day": 1, "slot": 5}]  # "can't" wins over "rather not"
    assert client.get("/me/availability", headers=prof).json() == r


def test_daily_limit_per_professor(client, admin, demo):
    r = client.put("/admin/settings", headers=admin,
                   json={"max_sessions_per_day_per_professor": 2}).json()
    assert r["changed"] == ["max_sessions_per_day_per_professor"]
    gen = client.post("/admin/timetable/generate", headers=admin).json()
    assert gen["saved"] and gen["conflicts"] == []
    with SessionLocal() as db:
        per_day = Counter((s.professor_id, s.day) for s in db.scalars(select(Session)))
    assert max(per_day.values()) <= 2
    assert client.put("/admin/settings", headers=admin,
                      json={"max_sessions_per_day_per_professor": 0}).status_code == 422


def test_rank_is_kept_and_editable(client, admin):
    lv = client.post("/admin/levels", json={"name": "L1", "headcount": 30}, headers=admin).json()
    m1 = client.post("/admin/modules", json={"level_id": lv["id"], "name": "A"}, headers=admin).json()
    m2 = client.post("/admin/modules", json={"level_id": lv["id"], "name": "B"}, headers=admin).json()
    p = client.post("/admin/professors", headers=admin, json={
        "name": "Test Prof", "teaches": [{"module_id": m2["id"], "rank": 2},
                                         {"module_id": m1["id"], "rank": 1}]}).json()
    assert [t["module_id"] for t in p["teaches"]] == [m1["id"], m2["id"]]
    assert [t["rank"] for t in p["teaches"]] == [1, 2]
