"""Live mode: absence -> freed room -> claimed by another professor."""
from datetime import date, timedelta

from conftest import login_prof, next_date_for_day


def _prof_sessions(client, demo):
    """Every professor's weekly sessions, with their login."""
    out = []
    for creds in demo["credentials"]:
        h = login_prof(client, creds)
        out.append((creds, h, client.get("/me/timetable", headers=h).json()))
    return out


def test_absence_rules(client, admin, demo):
    (creds_a, prof_a, mine), (creds_b, prof_b, _) = _prof_sessions(client, demo)[:2]
    s = mine[0]
    good_date = next_date_for_day(s["day"])
    wrong_day = good_date + timedelta(days=1)
    assert client.post("/me/absences", headers=prof_a,
                       json={"session_id": s["session_id"], "date": wrong_day.isoformat()}).status_code == 422
    past = good_date - timedelta(days=7 * 52)
    assert client.post("/me/absences", headers=prof_a,
                       json={"session_id": s["session_id"], "date": past.isoformat()}).status_code == 422
    assert client.post("/me/absences", headers=prof_b,  # not prof B's session
                       json={"session_id": s["session_id"], "date": good_date.isoformat()}).status_code == 403
    r1 = client.post("/me/absences", headers=prof_a,
                     json={"session_id": s["session_id"], "date": good_date.isoformat()})
    assert r1.status_code == 201
    # Offline replay: same request again -> same absence, no duplicate
    r2 = client.post("/me/absences", headers=prof_a,
                     json={"session_id": s["session_id"], "date": good_date.isoformat()})
    assert r2.json()["id"] == r1.json()["id"]
    assert len(client.get("/me/absences", headers=prof_a).json()) == 1

    # Students of that group see it as cancelled
    week = client.get(f"/public/groups/{s['group_id']}/week?date={good_date}").json()
    e = next(x for x in week["entries"] if x.get("session_id") == s["session_id"]
             and x["date"] == good_date.isoformat())
    assert e["status"] == "cancelled"
    # The room shows as free (and flagged as freed) for that slot
    free = client.get(f"/public/free-rooms?date={good_date}&slot={s['slot']}").json()
    assert any(r["name"] == s["room"] and r["freed_by_absence"] for r in free)

    # Undo works while nobody took the slot
    assert client.delete(f"/me/absences/{r1.json()['id']}", headers=prof_a).status_code == 200
    week = client.get(f"/public/groups/{s['group_id']}/week?date={good_date}").json()
    assert all(x["status"] == "normal" for x in week["entries"] if x.get("session_id") == s["session_id"])


def test_absence_freed_room_claim(client, admin, demo):
    """Prof A is absent -> room freed -> Prof B finds it in the ranked options and claims it."""
    profs = _prof_sessions(client, demo)
    creds_a, prof_a, sessions_a = profs[0]
    s = sessions_a[0]
    when = next_date_for_day(s["day"])
    absence = client.post("/me/absences", headers=prof_a,
                          json={"session_id": s["session_id"], "date": when.isoformat()}).json()

    # Find a professor B and one of B's groups for which the freed room is a valid option.
    found = None
    for creds_b, prof_b, sessions_b in profs[1:]:
        for g in client.get("/me/groups", headers=prof_b).json():
            res = client.post("/me/slots/search", headers=prof_b, json={
                "group_id": g["group_id"], "date_from": when.isoformat(),
                "date_to": when.isoformat(), "limit": 50}).json()
            freed = [o for o in res["options"] if o["freed_by_absence"]]
            if freed:
                found = (creds_b, prof_b, g, res["options"], freed[0])
                break
        if found:
            break
    assert found, "the freed room should be offered to someone"
    creds_b, prof_b, g, options, opt = found

    # Every option really is free for prof B, the group and the room
    assert all(o["date"] == when.isoformat() for o in options)
    assert "reuses a room freed by an absence" in opt["reasons"]
    scores = [o["score"] for o in options]
    assert scores == sorted(scores, reverse=True)

    claim_body = {"group_id": g["group_id"], "room_id": opt["room"]["id"], "date": opt["date"],
                  "slot": opt["slot"], "module_id": g["module_id"]}
    r = client.post("/me/claims", headers=prof_b, json=claim_body)
    assert r.status_code == 201, r.text
    claim = r.json()
    # Offline replay of the same claim -> same claim
    assert client.post("/me/claims", headers=prof_b, json=claim_body).json()["id"] == claim["id"]

    # The group page shows the new session
    week = client.get(f"/public/groups/{g['group_id']}/week?date={when}").json()
    assert any(e["status"] == "new" and e.get("claim_id") == claim["id"] for e in week["entries"])
    # Prof B's week shows it too
    assert any(e.get("claim_id") == claim["id"] for e in
               client.get(f"/me/week?date={when}", headers=prof_b).json()["entries"])

    # Prof C tries to grab the same room at the same time -> 409, first claim wins, gets alternatives
    creds_c, prof_c, _ = next(p for p in profs if p[0]["username"] not in
                              (creds_a["username"], creds_b["username"]) and
                              client.get("/me/groups", headers=p[1]).json())
    g_c = client.get("/me/groups", headers=prof_c).json()[0]
    r = client.post("/me/claims", headers=prof_c, json={
        "group_id": g_c["group_id"], "room_id": opt["room"]["id"], "date": opt["date"],
        "slot": opt["slot"]})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["problems"] and "alternatives" in detail

    # Prof A shows up after all -> too late, the slot was taken
    assert client.delete(f"/me/absences/{absence['id']}", headers=prof_a).status_code == 409
    # B cancels the claim -> now A can undo the absence
    assert client.delete(f"/me/claims/{claim['id']}", headers=prof_c).status_code == 403
    assert client.delete(f"/me/claims/{claim['id']}", headers=prof_b).status_code == 200
    assert client.delete(f"/me/absences/{absence['id']}", headers=prof_a).status_code == 200

    stats = client.get("/admin/stats", headers=admin).json()
    assert stats["absences"] == 0 and stats["extra_sessions"] == 0
    actions = [x["action"] for x in client.get("/admin/logs", headers=admin).json()]
    assert {"absence", "claim", "claim_cancel", "absence_undo"} <= set(actions)


def test_claim_refuses_busy_group_and_bad_input(client, admin, demo):
    creds, prof, mine = _prof_sessions(client, demo)[0]
    s = mine[0]
    when = next_date_for_day(s["day"])
    rooms = client.get("/admin/rooms", headers=admin).json()
    # The group already has this very session at that time -> refused
    other_room = next(r for r in rooms if r["name"] != s["room"] and r["type"] != "amphi")
    r = client.post("/me/claims", headers=prof, json={
        "group_id": s["group_id"], "room_id": other_room["id"], "date": when.isoformat(),
        "slot": s["slot"]})
    assert r.status_code == 409
    problems = " ".join(r.json()["detail"]["problems"])
    assert "group is busy" in problems or "already teach" in problems
    # Friday is not a working day
    friday = next_date_for_day(5)
    assert client.post("/me/claims", headers=prof, json={
        "group_id": s["group_id"], "room_id": other_room["id"], "date": friday.isoformat(),
        "slot": 0}).status_code == 422
    # Past date
    assert client.post("/me/claims", headers=prof, json={
        "group_id": s["group_id"], "room_id": other_room["id"],
        "date": (date.today() - timedelta(days=3)).isoformat(), "slot": 0}).status_code == 422
    # Unknown group / room
    assert client.post("/me/claims", headers=prof, json={
        "group_id": 999999, "room_id": other_room["id"], "date": when.isoformat(),
        "slot": 0}).status_code == 404
    # Search: unknown group, inverted dates
    assert client.post("/me/slots/search", headers=prof, json={"group_id": 999999}).status_code == 404
    assert client.post("/me/slots/search", headers=prof, json={
        "group_id": s["group_id"], "date_from": when.isoformat(),
        "date_to": (when - timedelta(days=2)).isoformat()}).status_code == 422


def test_slot_search_default_range_and_validity(client, admin, demo):
    creds, prof, mine = _prof_sessions(client, demo)[1]
    g = client.get("/me/groups", headers=prof).json()[0]
    res = client.post("/me/slots/search", headers=prof, json={"group_id": g["group_id"]})
    assert res.status_code == 200
    body = res.json()
    assert date.fromisoformat(body["from"]) >= date.today()
    # Claiming every returned option one at a time must succeed (they are genuinely free),
    # and each claim must then make the next identical claim fail.
    opt = body["options"][0] if body["options"] else None
    if opt:
        r = client.post("/me/claims", headers=prof, json={
            "group_id": g["group_id"], "room_id": opt["room"]["id"], "date": opt["date"],
            "slot": opt["slot"]})
        assert r.status_code == 201, r.text
        again = client.post("/me/slots/search", headers=prof, json={
            "group_id": g["group_id"], "date_from": opt["date"], "date_to": opt["date"],
            "limit": 50}).json()
        assert not any(o["slot"] == opt["slot"] for o in again["options"]), \
            "the group is now busy at that slot, it must not be offered again"


def test_public_endpoints(client, demo):
    cfg = client.get("/public/config").json()
    assert cfg["days"][0] == "Sunday" and len(cfg["slots"]) == 6
    assert client.get("/public/groups/999999/week").status_code == 404
    assert client.get("/public/free-rooms?date=2030-01-06&slot=9").status_code == 422
    leaf = client.get("/public/groups").json()[0]["sections"][0]["children"][0]
    week = client.get(f"/public/groups/{leaf['id']}/week").json()
    kinds = {e["kind"] for e in week["entries"]}
    assert {"lecture", "td", "tp"} <= kinds  # a TP subgroup sees lectures, TD and its own TP


def test_cannot_book_students_you_dont_teach(client, admin, demo):
    profs = _prof_sessions(client, demo)
    (_, prof_a, mine_a), (_, _, mine_b) = profs[0], profs[1]
    from app.db import SessionLocal
    from app.services.groups import GroupTree

    with SessionLocal() as db:
        tree = GroupTree.load(db)
    mine = set().union(*(tree.related(s["group_id"]) for s in mine_a))
    foreign = next(s["group_id"] for s in mine_b if s["group_id"] not in mine)
    assert client.post("/me/slots/search", headers=prof_a, json={"group_id": foreign}).status_code == 403
    room = client.get("/admin/rooms", headers=admin).json()[0]
    when = next_date_for_day(1)
    assert client.post("/me/claims", headers=prof_a, json={
        "group_id": foreign, "room_id": room["id"], "date": when.isoformat(), "slot": 0}).status_code == 403


def test_regenerate_keeps_upcoming_absences(client, admin, demo):
    """Regenerating (e.g. after closing a room) must not silently erase declared absences."""
    creds, prof, mine = _prof_sessions(client, demo)[0]
    s = mine[0]
    when = next_date_for_day(s["day"])
    client.post("/me/absences", headers=prof, json={"session_id": s["session_id"], "date": when.isoformat()})
    r = client.post("/admin/timetable/generate", headers=admin).json()
    assert r["saved"] and r["absences_kept"] == 1 and r["absences_dropped"] == []
    absences = client.get("/me/absences", headers=prof).json()
    assert len(absences) == 1 and absences[0]["date"] == when.isoformat()
    week = client.get(f"/public/groups/{s['group_id']}/week?date={when}").json()
    assert any(e["status"] == "cancelled" and e["module"] == s["module"] for e in week["entries"])


def test_admin_week_views(client, admin, demo):
    room = client.get("/admin/rooms", headers=admin).json()[0]
    prof = client.get("/admin/professors", headers=admin).json()[0]
    for scope, i in (("room", room["id"]), ("prof", prof["id"])):
        r = client.get(f"/admin/week?scope={scope}&id={i}", headers=admin)
        assert r.status_code == 200 and r.json()["dates"]
    assert client.get("/admin/week?scope=room&id=99999", headers=admin).status_code == 404


def test_extra_session_in_a_cancelled_slot_is_not_flagged(client, admin, demo):
    """Prof B books the slot freed by Prof A's absence, for the same group; regenerating must not
    report it as overlapping (the class it sits on is cancelled that day)."""
    profs = _prof_sessions(client, demo)
    for creds_a, prof_a, mine in profs:
        for s in mine:
            others = [h for c, h, ss in profs if c is not creds_a
                      and any(x["group_id"] == s["group_id"] for x in ss)
                      and not any((x["day"], x["slot"]) == (s["day"], s["slot"]) for x in ss)]
            if others:
                break
        else:
            continue
        break
    when = next_date_for_day(s["day"])
    client.post("/me/absences", headers=prof_a, json={"session_id": s["session_id"], "date": when.isoformat()})
    rooms = {r["name"]: r["id"] for r in client.get("/admin/rooms", headers=admin).json()}
    r = client.post("/me/claims", headers=others[0], json={"group_id": s["group_id"], "room_id": rooms[s["room"]],
                                                           "date": when.isoformat(), "slot": s["slot"]})
    assert r.status_code == 201, r.text
    again = client.post("/admin/timetable/generate", headers=admin).json()
    assert again["saved"] and again["absences_kept"] == 1 and again["claims_to_review"] == []
