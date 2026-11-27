"""Runs three demo scenarios end to end, without a server:

    python scripts/demo_cases.py

1. A classroom closes for repairs.
2. A professor can no longer teach on Sundays.
3. A professor is absent and another one books the freed room for an extra session.

Uses a temporary database (real data is never touched). The admin login is read from .env
(ADMIN_USERNAME / ADMIN_PASSWORD).
"""
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/demo_cases.db"
os.environ["DEMO_MODE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

LINE = "-" * 64


def title(text):
    print(f"\n{LINE}\n{text}\n{LINE}")


def main():
    with TestClient(app) as c:
        tok = c.post("/auth/login", json={"username": settings.admin_username,
                                          "password": settings.admin_password}).json()["token"]
        A = {"Authorization": f"Bearer {tok}"}
        cfg = lambda: c.get("/public/config").json()  # noqa: E731

        title("SETUP: synthetic department -> one click 'Generate'")
        seed = c.post("/admin/demo/seed", headers=A).json()
        print(f"{seed['levels']} levels, {seed['rooms']} rooms, {seed['professors']} professors")
        g = c.post("/admin/timetable/generate", headers=A).json()
        n_groups = sum(1 + len(s["td"]) + sum(len(t["tp"]) for t in s["td"])
                       for lv in c.get("/admin/groups", headers=A).json()["levels"] for s in lv["sections"])
        print(f"{n_groups} groups built from headcounts")
        print(f"Solver: {g['solver']} | {g['placed']}/{g['requirements']} sessions placed in "
              f"{g['seconds']} s | clashes: {len(g['conflicts'])} | "
              f"gaps per group per week: {g['gaps_per_group_per_week']}")

        title("CASE 1: 'A classroom is closed for repairs'")
        rooms = c.get("/admin/rooms", headers=A).json()
        room = next(r for r in rooms if r["name"] == "Room 1")
        c.patch(f"/admin/rooms/{room['id']}", json={"active": False}, headers=A)
        g = c.post("/admin/timetable/generate", headers=A).json()
        print(f"Regenerated in {g['seconds']} s: {g['placed']}/{g['requirements']} placed, "
              f"clashes: {len(g['conflicts'])}, only {g['sessions_moved']} sessions moved.")

        title("CASE 2: 'Prof X can't teach on Sundays anymore'")
        creds = seed["credentials"][0]
        profs = c.get("/admin/professors", headers=A).json()
        px = next(p for p in profs if p["username"] == creds["username"])
        c.put(f"/admin/professors/{px['id']}/availability", headers=A,
              json={"unavailable": [{"day": 0, "slot": s} for s in range(len(cfg()["slots"]))]})
        g = c.post("/admin/timetable/generate", headers=A).json()
        P = {"Authorization": "Bearer " + c.post("/auth/login", json=creds).json()["token"]}
        names = cfg()["days"]
        days = sorted({s["day"] for s in c.get("/me/timetable", headers=P).json()})
        print(f"{px['name']} now teaches on: {', '.join(names[d] for d in days)} (no Sunday). "
              f"Clashes: {len(g['conflicts'])}, sessions moved: {g['sessions_moved']}")

        title("CASE 3: Prof Y is absent, Prof Z needs an extra session")
        heads = [{"Authorization": "Bearer " + c.post("/auth/login", json=cr).json()["token"]}
                 for cr in seed["credentials"]]
        y = heads[1]
        s = c.get("/me/timetable", headers=y).json()[0]
        # Next date on which this weekly session happens (this week, or next week if passed).
        week = c.get(f"/public/groups/{s['group_id']}/week?date={date.today()}").json()
        d = date.fromisoformat(week["dates"][s["day"]])
        if d <= date.today():
            week = c.get(f"/public/groups/{s['group_id']}/week?date={d + timedelta(days=7)}").json()
            d = date.fromisoformat(week["dates"][s["day"]])
        c.post("/me/absences", headers=y, json={"session_id": s["session_id"], "date": d.isoformat()})
        print(f"Prof Y cancels {s['module']} ({s['group']}) on {names[s['day']]} {d} "
              f"at {cfg()['slots'][s['slot']]} -> {s['room']} is free.")
        for z in heads[2:]:
            for grp in c.get("/me/groups", headers=z).json():
                res = c.post("/me/slots/search", headers=z, json={
                    "group_id": grp["group_id"], "date_from": d.isoformat(),
                    "date_to": d.isoformat(), "limit": 3}).json()
                freed = [o for o in res.get("options", []) if o["freed_by_absence"]]
                if not freed:
                    continue
                print(f"Prof Z asks for 1h30 with {grp['group']} that day. Top options:")
                for i, o in enumerate(res["options"], 1):
                    print(f"  {i}. {o['day']} {o['time']} {o['room']['name']:<8} "
                          f"score {o['score']:>5}  {'; '.join(o['reasons'])}")
                o = freed[0]
                r = c.post("/me/claims", headers=z, json={
                    "group_id": grp["group_id"], "room_id": o["room"]["id"], "date": o["date"],
                    "slot": o["slot"], "module_id": grp["module_id"]})
                print(f"Prof Z claims {o['room']['name']} at {o['time']} -> HTTP {r.status_code}")
                week = c.get(f"/public/groups/{grp['group_id']}/week?date={d}").json()
                badge = next(e for e in week["entries"] if e["status"] == "new")
                print(f"{grp['group']}'s page now shows: {badge['module']} [NEW SESSION] in {badge['room']}")
                other = heads[-1]
                r2 = c.post("/me/claims", headers=other, json={
                    "group_id": c.get("/me/groups", headers=other).json()[0]["group_id"],
                    "room_id": o["room"]["id"], "date": o["date"], "slot": o["slot"]})
                print(f"Someone else tries the same room and time -> HTTP {r2.status_code} "
                      f"(first claim wins), {len(r2.json()['detail'].get('alternatives', []))} "
                      f"alternatives offered")
                check = c.get("/admin/timetable/check", headers=A).json()
                print(f"\nFinal check of the whole timetable: "
                      f"{'0 clashes' if check['ok'] else check['conflicts']}")
                return
        print("No professor could use the freed room in this dataset.")


if __name__ == "__main__":
    main()
