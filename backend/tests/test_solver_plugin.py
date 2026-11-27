"""Solver plug-ins (SOLVER_MODULE in .env): a bad result is never saved, and a broken
plug-in falls back to the built-in solver."""
import sys
import types


def _install(monkeypatch, name, **functions):
    mod = types.ModuleType(name)
    for k, v in functions.items():
        setattr(mod, k, v)
    monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setenv("SOLVER_MODULE", name)


def test_plugged_solver_is_used_and_checked(client, admin, monkeypatch):
    client.post("/admin/demo/seed", headers=admin)

    def bad_solve(data):  # everything in the same room at the same time
        room = data["rooms"][0]["id"]
        prof = data["can_teach"][0]["prof_id"]
        return {"assignments": [{"requirement_id": r["id"], "prof_id": prof, "room_id": room,
                                 "day": 0, "slot": 0} for r in data["requirements"][:5]],
                "unscheduled": []}

    _install(monkeypatch, "fake_ai_solver", solve=bad_solve)
    r = client.post("/admin/timetable/generate", headers=admin).json()
    assert r["solver"] == "fake_ai_solver"
    assert r["conflicts"] and r["saved"] is False
    assert client.get("/admin/stats", headers=admin).json()["sessions_per_week"] == 0

    from app.services import fallback_solver

    _install(monkeypatch, "fake_ai_solver", solve=fallback_solver.solve)
    r = client.post("/admin/timetable/generate", headers=admin).json()
    assert r["solver"] == "fake_ai_solver" and r["saved"] and r["conflicts"] == []


def test_broken_plugin_falls_back(client, admin, monkeypatch):
    client.post("/admin/demo/seed", headers=admin)

    def crash(data):
        raise ValueError("model file missing")

    _install(monkeypatch, "crashing_solver", solve=crash)
    r = client.post("/admin/timetable/generate", headers=admin).json()
    assert r["saved"] and r["solver"] == "built-in" and "model file missing" in r["warning"]

    monkeypatch.setenv("SOLVER_MODULE", "this.module.does.not.exist")
    r = client.post("/admin/timetable/generate", headers=admin).json()
    assert r["saved"] and r["solver"] == "built-in" and r["warning"]
    assert client.get("/health").json()["solver_warning"]


def test_contract_shape(client, admin):
    """The data passed to a solver plug-in: plain JSON-serialisable dicts."""
    import json

    from app.db import SessionLocal
    from app.services.solver_adapter import build_input

    client.post("/admin/demo/seed", headers=admin)
    client.post("/admin/groups/build", headers=admin)
    with SessionLocal() as db:
        data = build_input(db)
    json.dumps(data)
    assert set(data) >= {"days", "slots", "rooms", "groups", "professors", "can_teach",
                         "requirements", "room_types_for", "options", "previous"}
    assert set(data["requirements"][0]) == {"id", "module_id", "module", "group_id", "kind", "size"}
    assert data["days"][0] == "Sunday" and data["slots"][1] == "09:30-11:00"


def test_column_mapper_plugin(client, admin, monkeypatch):
    def map_columns(kind, headers, fields):
        return {"capacity": "Seats (approx.)"} if "capacity" in fields else {}

    mod = types.ModuleType("fake_mapper")
    mod.map_columns = map_columns
    monkeypatch.setitem(sys.modules, "fake_mapper", mod)
    monkeypatch.setenv("COLUMN_MAPPER_MODULE", "fake_mapper")
    p = client.post("/admin/import/preview", headers=admin, data={"kind": "rooms"},
                    files={"file": ("r.csv", "Room,Seats (approx.)\nRoom 1,40\n".encode())}).json()
    assert p["mapping"]["capacity"]["method"] == "llm" and p["rows"][0]["capacity"] == 40
