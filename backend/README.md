# Backend

FastAPI + SQLite. Reads the department's existing files, generates a clash-free timetable in
one click, and runs the live mode: an absence frees a room, another professor claims it.

## Run it

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then set ADMIN_USERNAME and ADMIN_PASSWORD in .env
uvicorn app.main:app --reload
```

Open **http://localhost:8000/docs**: every endpoint is listed and can be tried in the browser.
The database file and the admin account are created automatically on first start.

## Test it

```bash
pytest -q                       # about 40 tests, ~30 s
python scripts/demo_cases.py    # runs 3 demo scenarios on a temporary database
```

## Fits into the department as it is

- **Reads what already exists.** Rooms, levels, modules and professors come from the PDF,
  Excel or CSV files the department already has. Headers are matched automatically
  (French, English, Arabic) and the admin checks a preview before anything is saved.
  Re-importing an updated file updates the data instead of duplicating it.
- **Gives back what they already use.** Timetables export to Excel and PDF in the usual
  days × time slots layout.
- **Nothing to reset, nothing to edit by hand.** The database creates itself on first start.
  Days, time slots, group sizes and room rules are settings the admin changes in the app;
  the timetable regenerates on its own when needed, moving as few sessions as possible, and
  keeps the absences already declared.
- **Nothing to install for users.** Students open their group's page without an account;
  professors get a login from the imported list.
- **Safe by design.** The solver's output is re-checked against every rule before saving.
  Demo data can only be loaded into an empty database (and only with `DEMO_MODE=1`).

## Endpoints (summary)

| Who    | Endpoint                                                                                 | What                                                   |
| ------ | ---------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| all    | `POST /auth/login`                                                                       | returns a token; send it as `Authorization: Bearer …`  |
| admin  | `/admin/rooms`, `/admin/levels`, `/admin/modules`, `/admin/professors`                   | create / list / edit / delete                          |
| admin  | `POST /admin/import/preview` → `POST /admin/import/commit`                               | PDF / Excel / CSV import, with preview                 |
| admin  | `GET /admin/settings`, `PUT /admin/settings`                                             | days, time slots, group sizes, room rules              |
| admin  | `POST /admin/timetable/generate`                                                         | one click: groups, timetable, checks, save             |
| admin  | `PATCH /admin/sessions/{id}`                                                             | move a session by hand (refused if it creates a clash) |
| admin  | `GET /admin/groups`, `GET /admin/stats`, `GET /admin/logs`, `GET /admin/timetable/check` | dashboard                                              |
| prof   | `GET /me/timetable`, `GET /me/week?date=`                                                | my sessions, my live week                              |
| prof   | `PUT /me/availability`                                                                   | weekly grid of slots I can't teach                     |
| prof   | `POST /me/absences`, `DELETE /me/absences/{id}`                                          | cancel one date of a session / undo                    |
| prof   | `POST /me/slots/search`                                                                  | ranked free (date, time, room) for a group I teach     |
| prof   | `POST /me/claims`, `DELETE /me/claims/{id}`                                              | book an extra session (first claim wins)               |
| public | `GET /public/config`, `GET /public/groups`, `GET /public/groups/{id}/week?date=`         | student pages                                          |
| public | `GET /public/free-rooms?date=&slot=`, `GET /export/excel`, `GET /export/pdf`             | free rooms, downloads                                  |

## AI plug-ins

Set in `.env`, no code change in the backend:

- `SOLVER_MODULE=ai.solver`: a module with `solve(data) -> result`. The data format is at the top
  of `app/services/solver_adapter.py`. Empty = the built-in solver. If the plug-in is missing or
  crashes, the built-in solver takes over and the response says why.
- `COLUMN_MAPPER_MODULE=ai.column_mapper`: a module with `map_columns(kind, headers, fields)`,
  asked about the columns the dictionary could not match during an import.

## Configuration

Technical settings are in `.env` (see `.env.example`): admin account, database, login duration,
allowed frontend address, demo mode, plug-ins. The department's rules are not in files: the admin
edits them from the app (`/admin/settings`).
