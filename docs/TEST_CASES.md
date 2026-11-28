# Manual test checklist

Run on a fresh database: `cd backend && rm -f timetable.db && uvicorn app.main:app`, plus the
web app (`cd frontend && npm run dev`). Admin login: `ADMIN_USERNAME` / `ADMIN_PASSWORD` in
`backend/.env`. Professor logins: shown once after "Load demo department" (copy them), or
Professors → "New password". Test each section on a computer **and** on a phone.

Automated coverage already in place: `cd backend && pytest -q` (50 tests) and
`python scripts/demo_cases.py` (the 3 jury cases).

## A. Jury cases (rehearse these first)

- [ ] **A1 Room closed.** Rooms → Close the busiest classroom → Timetable → Generate. Expect:
      saved, 0 clashes, "sessions moved" ≈ the number of sessions that were in that room, the
      closed room is gone from every grid (check "By room": empty week).
- [ ] **A2 Professor can't teach on a day.** Log in as a professor → My availability → mark a
      whole day "Can't" → Save. Admin → Generate. Expect: 0 clashes, that professor has nothing
      on that day (Timetable → By professor), few sessions moved.
- [ ] **A3 Absence + extra session.** Prof Y: My week → tap a future class → "I'll be absent".
      Prof Z (teaches a group free at that time): Extra session → pick group → Find free slots.
      Expect: the freed room near the top with the "Freed room" label → Book → "Booked".
      Student page of Prof Y's group: "Cancelled". Student page of Prof Z's group: "New session".
- [ ] **A4 First claim wins.** Two browsers, two professors, same option, click Book in both.
      Expect: one "Booked", the other "This slot is no longer available" + new options.

## B. Admin: data and import

- [ ] B1 Empty database → Dashboard shows "Start by adding…" with Import / Load demo department.
- [ ] B2 Load demo department → professor logins dialog appears once → Copy all works.
- [ ] B3 Load demo again on a non-empty database → refused with a clear message (409).
- [ ] B4 Import order levels → rooms → modules → professors, from CSV (`;` and `,`), Excel and a
      PDF table. Each: preview shows detected columns, rows editable, Save → counts.
- [ ] B5 Import a file with unusual headers ("Cap. accueil", "Nbre de places assises") → the
      column is matched as "AI suggestion" (needs the model in `models/`); without the model it
      shows "(not in the file)" and you pick it by hand.
- [ ] B6 Change a column in the mapping dropdown → the preview rows update.
- [ ] B7 Missing required column (e.g. rooms without capacity) → Save disabled, message shown.
- [ ] B8 Edit a cell in the preview, delete a row → only the edited rows are saved.
- [ ] B9 Import the same file twice → second time "0 new, N updated" (no duplicates).
- [ ] B10 Levels split in two columns (Année + Spécialité) → levels named "L3 ISIL"; modules
      file with Année + Spécialité links to the right level (no "level not found" warning).
- [ ] B11 Professors file with "Charge max (h/sem)" = 15 → max 10 sessions (15 h / 1h30).
- [ ] B12 Professors file with one wish per row + "Ordre de préférence" → ranks kept.
- [ ] B13 Modules imported before levels → warning "level not found", rows skipped, no crash.
- [ ] B14 Professors import → new logins shown once with passwords.
- [ ] B15 Wrong file type / empty file / file over 10 MB → clear error, nothing saved.
- [ ] B16 Rooms: add, edit (type, seats), close, reopen, delete. Search filters the list.
- [ ] B17 Levels: add, edit headcount, delete (asks to confirm). Modules link filters by level.
- [ ] B18 Modules: add with 0/1/2 per week of each kind, edit, delete, filter by level.
- [ ] B19 Professors: add (password shown once), edit name / max per week (empty = default),
      add modules, tick lecture/TD/TP, reorder with ↑ ↓ (rank), remove, delete professor.
- [ ] B20 Professors → Availability: fill the grid for a professor, Save, the "Filled" badge appears.
- [ ] B21 Professors → New password: old password stops working, new one works.
- [ ] B22 Duplicate names (room, level, professor) → refused with a message, no crash.

## C. Admin: generation, timetable, settings

- [ ] C1 Generate on the demo → 195/195 placed, 0 clashes, time ≈ 10 s, gaps shown.
- [ ] C2 Generate again with no change → 0 sessions moved.
- [ ] C3 Unplaceable data (e.g. a module whose only professor has max 1 session, or a TP with
      no lab big enough) → saved with a list "could not be placed" and the reason.
- [ ] C4 Generate with no levels → error "No levels yet".
- [ ] C5 Timetable: By group / By professor / By room tabs; select another item; previous /
      next week; "This week" button returns.
- [ ] C6 Selecting a whole section shows its groups' classes with the group name on each card.
- [ ] C7 Tap a session → Move to a free slot → moved. Move onto a clash → refused, clash listed.
- [ ] C8 Tap a session → "Professor absent on …" → card shows Cancelled.
- [ ] C9 Check for clashes → "0 clashes".
- [ ] C10 PDF / Excel downloads (one item, and "All … (Excel)") open in Excel / a PDF reader in
      the usual days × slots layout.
- [ ] C11 Settings: change max sessions per day per professor → Save (no regeneration) →
      Generate → no professor above the limit.
- [ ] C11b Settings: "Sessions in a row before a break" = 2 → Generate → most groups get a free
      slot after 2 classes (preferred, not strict: a few runs of 3 can remain).
- [ ] C12 Settings: add Saturday as a working day → saved and the timetable regenerates; grids
      everywhere show Saturday. Change the first day of the week.
- [ ] C13 Settings: add / remove / edit a time slot; invalid format or overlapping slot → error.
- [ ] C14 Settings: change TD group size → groups rebuilt, timetable regenerated.
- [ ] C15 Settings: turn on "Split TD groups into TP subgroups" → TP subgroups appear.
- [ ] C16 Settings: room rules matrix (e.g. allow lectures only in lecture halls) → regenerates.
- [ ] C17 Settings: Back to defaults → Save.
- [ ] C18 Dashboard numbers match (sessions, absences, extra sessions, freed rooms reused).
- [ ] C19 Activity log lists imports, generations, absences, bookings with who and when.

## D. Professor

- [ ] D1 Login with a wrong password → error. Correct → "My week".
- [ ] D2 My week shows only this professor's classes; previous / next week work.
- [ ] D3 Declare an absence on a future class → Cancelled; Undo → back to normal.
- [ ] D4 Past class → no absence button ("This date has passed").
- [ ] D5 Undo an absence after someone booked the freed slot → refused with who booked it.
- [ ] D6 Extra session: "Coming days", "The week after", "Choose dates" (a range > 31 days →
      error). Options show reasons, "Freed room" label, "+N other rooms free".
- [ ] D7 Book an option → it appears in My week as "New session" and in Absences & bookings.
- [ ] D8 Cancel an extra session from My week and from Absences & bookings.
- [ ] D9 A professor with no classes → Extra session says there is no group.
- [ ] D10 Availability: tap cycles Available → Can't → Rather not → Available; Save; reload the
      page → kept. The admin sees the same grid.
- [ ] D11 "Rather not" slots: Generate → the professor is placed there only if unavoidable.
- [ ] D12 Professor opening an /admin page → sent back to their own space.
- [ ] D13 Log out → back to the home page; /prof now asks to log in.

## E. Students (no account)

- [ ] E1 Home lists levels and groups; a group opens its live week.
- [ ] E2 Cancelled class shows the "Cancelled" label and is struck through; extra session shows
      "New session".
- [ ] E3 The group page also shows the section's lectures.
- [ ] E4 Share → QR code and link; scanning it on a phone opens the same page.
- [ ] E5 PDF / Excel download of the group.
- [ ] E6 Reopen the home page → "Open L1 INFO - G3" shortcut to the last group viewed.
- [ ] E7 Free rooms: pick a date and time → list of free rooms, freed ones labelled.
- [ ] E8 On a Friday / Saturday the page shows the coming week by default.
- [ ] E9 Before any generation → "No timetable published yet".

## F. Offline and phones (use the production build: `npm run build && npx vite preview`, or the hosted site)

- [ ] F1 Open a group page once, turn on airplane mode, reopen the app → the timetable is shown
      with "Offline: showing the copy saved …".
- [ ] F2 Install the app (Add to home screen) → opens full screen, works offline.
- [ ] F3 Professor offline: declare an absence → "will be sent when the connection returns",
      banner "1 action waiting". Back online → "Sent: Absence…", the class shows Cancelled.
- [ ] F4 Professor offline: book an extra session → queued; back online → booked, or a message
      if someone took the slot meanwhile.
- [ ] F5 Phone width: menu button opens the side menu; week becomes a day-by-day list; tables
      scroll sideways; dialogs fit the screen.
- [ ] F6 Server stopped while the app is open → clear "No connection to the server" message with
      "Try again", no blank page.

## G. Robustness and security

- [ ] G1 Log in, then delete the login on the server (or wait for expiry) → next action sends
      you back to the login page.
- [ ] G2 Without a login, /admin and /prof pages redirect to login; API calls return 401.
- [ ] G3 Professor calling admin API (e.g. GET /admin/rooms with their token) → 403.
- [ ] G4 Professor booking for a group they don't teach (via the API) → 403.
- [ ] G5 Absence on a date that isn't that class's weekday, or in the past (via the API) → 422.
- [ ] G6 Solver plug-in broken (set `SOLVER_MODULE=ai.nothing` in .env, restart) → Generate still
      works with the built-in solver and shows a warning; /health shows it.
- [ ] G7 Without the language model file → imports still work (dictionary only).
- [ ] G8 Two admins click Generate at the same time → both finish, 0 clashes (Check for clashes).
- [ ] G9 Restart the server → data, logins and the timetable are still there.
