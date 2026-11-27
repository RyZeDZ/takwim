"""The admin changes the department's rules from the app: no code change, no restart, no reset."""


def test_read_and_validate(client, admin):
    r = client.get("/admin/settings", headers=admin).json()
    assert r["rules"]["time_slots"][:2] == ["08:00-09:30", "09:30-11:00"]
    assert r["rules"]["week_days"][0] == "sunday"
    bad = [
        {"time_slots": ["08:00-09:30", "09:00-10:30"]},   # overlap
        {"time_slots": ["8h-9h30"]},                       # format
        {"week_days": ["monday", "funday"]},
        {"week_days": ["monday", "wednesday", "tuesday"]},  # order
        {"td_group_size": 0},
        {"room_types_for": {"lecture": ["kitchen"], "td": ["td"], "tp": ["lab"]}},
        {"colour": "blue"},
    ]
    for change in bad:
        assert client.put("/admin/settings", headers=admin, json=change).status_code == 422, change


def test_change_slots_regenerates_immediately(client, admin, demo):
    slots = ["08:00-09:30", "09:30-11:00", "11:00-12:30", "13:00-14:30", "14:30-16:00",
             "16:00-17:30", "17:30-19:00"]
    r = client.put("/admin/settings", headers=admin, json={"time_slots": slots}).json()
    assert r["changed"] == ["time_slots"]
    assert r["regenerated"]["saved"] and r["regenerated"]["conflicts"] == []
    assert client.get("/admin/settings", headers=admin).json()["rules"]["time_slots"] == slots
    assert client.get("/admin/timetable/check", headers=admin).json()["ok"]


def test_saturday_working_day(client, admin, demo):
    days = ["saturday", "sunday", "monday", "tuesday", "wednesday", "thursday"]
    r = client.put("/admin/settings", headers=admin, json={"week_days": days}).json()
    assert r["regenerated"]["saved"]
    from datetime import date

    from app.db import SessionLocal
    from app.rules import get_rules

    with SessionLocal() as db:
        rules = get_rules(db)
    assert rules.day_names == ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]
    assert rules.week_start(date.today()).weekday() == 5  # weeks now start on Saturday
    assert client.get("/admin/timetable/check", headers=admin).json()["ok"]


def test_group_size_change_rebuilds_groups(client, admin, demo):
    r = client.put("/admin/settings", headers=admin, json={"td_group_size": 25}).json()
    assert len(r["regenerated"]["groups_rebuilt_for"]) >= 1 and r["regenerated"]["saved"]
    levels = client.get("/admin/groups", headers=admin).json()["levels"]
    assert all(td["size"] <= 25 for lv in levels for s in lv["sections"] for td in s["td"])


def test_soft_change_does_not_regenerate(client, admin, demo):
    r = client.put("/admin/settings", headers=admin, json={"max_sessions_per_day_per_group": 3}).json()
    assert r["changed"] == ["max_sessions_per_day_per_group"] and r["regenerated"] is None
