# Backend

FastAPI + SQLite backend: smart timetables for the department.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env   # then set ADMIN_USERNAME and ADMIN_PASSWORD
uvicorn app.main:app --reload
```

Then open http://localhost:8000/docs.

## Test it

```bash
pytest -q
```

## Progress

- [x] Configuration from .env, database tables, department rules with defaults
- [ ] Admin (from .env) and professor logins
- [ ] Rooms, levels, modules, professors: create / list / edit / delete
- [ ] Import from PDF, Excel, CSV with automatic column matching and preview
- [ ] Groups built from headcounts (sections, TD, TP), demo department, stats
- [ ] One-click timetable generation with 0 clashes, admin-editable settings
- [ ] Live mode: absences, ranked free slots, claims, student week pages
- [ ] Excel and PDF export
- [ ] Jury demo script and AI plug-ins
