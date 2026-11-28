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


def test_in_a_row_setting_reaches_the_solver(client, admin, demo):
    from app.services.solver_adapter import build_input

    r = client.put("/admin/settings", headers=admin, json={"max_sessions_in_a_row": 2}).json()
    assert r["changed"] == ["max_sessions_in_a_row"]
    with SessionLocal() as db:
        assert build_input(db)["options"]["max_in_a_row"] == 2
    assert client.put("/admin/settings", headers=admin,
                      json={"max_sessions_in_a_row": 0}).status_code == 422


def test_cpsat_leaves_a_break_after_the_limit(monkeypatch):
    """One group, four classes, one day: with at most 3 in a row the solver leaves a break."""
    import pytest
    pytest.importorskip("ortools")
    from app.plugins import REPO_ROOT

    monkeypatch.syspath_prepend(str(REPO_ROOT))
    from ai import solver

    monkeypatch.setenv("SOLVER_TIME_LIMIT", "5")
    monkeypatch.setattr(solver, "_greedy_start", lambda data: [])
    data = {
        "days": ["Sunday"], "slots": [f"s{i}" for i in range(6)],
        "room_types_for": {"lecture": ["td"], "td": ["td"], "tp": ["lab"]},
        "options": {"max_sessions_per_day_group": 4, "max_sessions_per_day_prof": 6, "max_in_a_row": 3},
        "rooms": [{"id": 1, "name": "R1", "type": "td", "capacity": 40}],
        "groups": [{"id": 1, "name": "G1", "kind": "td", "size": 30, "parent_id": None}],
        "professors": [{"id": p, "name": f"P{p}", "max_sessions": 6, "unavailable": [], "avoid": []}
                       for p in range(1, 5)],
        "can_teach": [{"prof_id": p, "module_id": p, "kinds": ["td"], "rank": 1} for p in range(1, 5)],
        "requirements": [{"id": i, "module_id": i, "module": f"M{i}", "group_id": 1, "kind": "td", "size": 30}
                         for i in range(1, 5)],
        "previous": [],
    }
    slots = sorted(a["slot"] for a in solver.solve(data)["assignments"])
    assert len(slots) == 4
    runs = [1]
    for a, b in zip(slots, slots[1:]):
        runs.append(runs[-1] + 1 if b == a + 1 else 1)
    assert max(runs) <= 3
