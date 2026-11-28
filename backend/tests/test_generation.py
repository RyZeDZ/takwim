from sqlalchemy import select

from app.db import SessionLocal
from app.models import Professor, Room, Session


def test_generation_has_zero_clashes(client, admin, demo):
    assert client.get("/health").json()["solver"] == "built-in"
    r = client.post("/admin/timetable/generate", headers=admin).json()
    assert r["saved"] and r["conflicts"] == [] and r["unscheduled"] == []
    assert r["placed"] == r["requirements"] > 150
    assert r["seconds"] < 5
    assert client.get("/admin/timetable/check", headers=admin).json()["ok"]
    assert client.get("/admin/stats", headers=admin).json()["sessions_per_week"] == r["placed"]


def test_generate_needs_data_and_builds_groups_itself(client, admin):
    assert client.post("/admin/timetable/generate", headers=admin).status_code == 400
    client.post("/admin/demo/seed", headers=admin)
    r = client.post("/admin/timetable/generate", headers=admin).json()
    assert len(r["groups_rebuilt_for"]) == 8 and r["saved"]
    again = client.post("/admin/timetable/generate", headers=admin).json()
    assert again["groups_rebuilt_for"] == [] and again["sessions_moved"] == 0  # stable



def test_room_closed(client, admin, demo):
    """A room closes for repairs -> regenerate: still 0 clashes, and only the sessions that
    were in that room (plus a few knock-on moves) change. Uses the busiest classroom."""
    from collections import Counter

    with SessionLocal() as db:
        use = Counter(s.room_id for s in db.scalars(select(Session)) if s.room.type == "td")
        salle_id, in_room = use.most_common(1)[0]
    salle = next(r for r in client.get("/admin/rooms", headers=admin).json() if r["id"] == salle_id)
    client.patch(f"/admin/rooms/{salle['id']}", json={"active": False}, headers=admin)
    r = client.post("/admin/timetable/generate", headers=admin).json()
    assert r["saved"] and r["conflicts"] == [] and r["unscheduled"] == []
    assert in_room > 0 and in_room <= r["sessions_moved"] <= in_room * 3
    with SessionLocal() as db:
        assert not db.scalars(select(Session).where(Session.room_id == salle["id"])).first()


def test_prof_unavailable_sundays(client, admin, demo):
    """A professor can no longer teach on Sundays -> grid updated, timetable re-solved."""
    prof = next(p for p in client.get("/admin/professors", headers=admin).json()
                if p["username"] == demo["credentials"][0]["username"])
    client.put(f"/admin/professors/{prof['id']}/availability", headers=admin,
               json={"unavailable": [{"day": 0, "slot": s} for s in range(6)]})
    r = client.post("/admin/timetable/generate", headers=admin).json()
    assert r["saved"] and r["conflicts"] == []
    with SessionLocal() as db:
        days = {s.day for s in db.scalars(select(Session).where(Session.professor_id == prof["id"]))}
    assert days and 0 not in days


def test_manual_move(client, admin, demo):
    with SessionLocal() as db:
        prof = db.scalars(select(Professor)).first()
        mine = list(db.scalars(select(Session).where(Session.professor_id == prof.id)))
        a, b = mine[0], mine[1]
        rooms = [r.id for r in db.scalars(select(Room))]
    # Moving a onto the same time as b = the professor would be in two places.
    r = client.patch(f"/admin/sessions/{a.id}", headers=admin, json={"day": b.day, "slot": b.slot})
    assert r.status_code == 409 and "double-booked" in str(r.json())
    moved = False
    for d in range(5):
        for s in range(6):
            for room_id in rooms:
                if client.patch(f"/admin/sessions/{a.id}", headers=admin,
                                json={"day": d, "slot": s, "room_id": room_id}).status_code == 200:
                    moved = (d, s) != (a.day, a.slot)
                    break
            if moved:
                break
        if moved:
            break
    assert moved
    assert client.get("/admin/timetable/check", headers=admin).json()["ok"]
    assert client.patch("/admin/sessions/999999", headers=admin, json={"day": 1}).status_code == 404
    assert client.patch(f"/admin/sessions/{a.id}", headers=admin, json={"room_id": 999999}).status_code == 404
    assert client.patch(f"/admin/sessions/{a.id}", headers=admin, json={"day": 7}).status_code == 422
