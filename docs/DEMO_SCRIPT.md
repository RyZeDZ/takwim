# User journeys and video scripts

Short clips (30–75 s each) that can be shown on their own or cut together into the 2-minute
video. Each step: **what to do on screen** → *what to say*.

## Before recording

1. Fresh database: `cd backend && rm -f timetable.db`, `DEMO_MODE=1` in `backend/.env`, then
   `TZ=Africa/Algiers uvicorn app.main:app`. Web app: `cd frontend && npm run dev`
   (or the hosted site).
2. The language model is in `models/` (see `models/README.md`), otherwise the AI-suggestion step
   in clip 1 won't show.
3. Mock files: `data/demo-files/` (regenerate with `python backend/scripts/make_demo_files.py`).
4. Three browser windows: **Admin** (normal window), **Prof Y** and **Prof Z** (private
   windows), and a **phone** (or the browser's phone view, 390 px wide) for the student.
5. Zoom the browser to 110–125 %, hide bookmarks and notifications, record at 1080p.

## The three users in one line each

| Who | Journey |
| --- | --- |
| Admin (head of department) | Import the usual files → check the preview → Generate → share group links → handle changes with one click |
| Professor | My week → "I'll be absent" on a class → or: Extra session → ranked options → Book |
| Student | Open the group link / QR code → see this week with Cancelled / New session → works offline |

---

## Clip 1: From the department's files to a timetable (admin, ~75 s)

| Screen | Voice-over |
| --- | --- |
| Login as admin → empty Dashboard | *"Every semester the timetable is built by hand in Excel. Here, the department just uploads the files it already has."* |
| Import files → **Levels** → upload `1_niveaux.xlsx` | *"Headcounts per level, as an Excel file with French headers."* |
| Point at the "Detected columns" table → Save | *"Each column is recognised automatically. Nothing is saved before we check."* |
| **Rooms** → `2_salles.csv` → Save | *"The list of rooms, from a CSV."* |
| **Rooms** → `2bis_salles_bloc_D_entetes_inhabituels.csv` | *"This file uses unusual headers: 'Cap. accueil'. A small AI model running on this laptop, no internet, suggests the matches."* |
| Show "AI suggestion" on capacity; change **type** from "Bloc" to "Usage" → Save | *"The admin stays in control: one suggestion was wrong, we fix it in one click."* |
| **Modules** → `3_modules.pdf` → Save | *"Even a PDF of the official programme."* |
| **Professors** → `4_fiche_de_voeux.xlsx` → Save → logins table → Copy all | *"The professors' wish lists, in order of preference. Each professor gets a login."* |
| Timetable → **Generate** (wait ~10 s) | *"One click. The AI builds the groups from the headcounts and places every session."* |
| Summary: 172/172, 0 clashes, gaps | *"172 sessions, zero clashes, in ten seconds on an ordinary laptop."* |
| Scroll the grid "By group", switch to "By professor" | *"Every group, professor and room has its own timetable, exportable to Excel and PDF."* |

Shortcut for the other clips: Dashboard → **Load demo department** → Generate.

## Clip 2: Jury case 1, a room closes for repairs (admin, ~30 s)

| Screen | Voice-over |
| --- | --- |
| Timetable → By room → pick a busy classroom, show its week | *"Room 3 is closed for repairs from tomorrow."* |
| Rooms → **Close** on that room | |
| Timetable → **Generate** | *"We regenerate."* |
| Summary: 0 clashes, "sessions moved" ≈ the sessions that were in the room; By room → closed room is empty | *"Still zero clashes, and only the sessions that were in that room moved. Everyone else keeps their timetable."* |

## Clip 3: Jury case 2, a professor can't teach on Sundays anymore (~40 s)

| Screen | Voice-over |
| --- | --- |
| Prof window: log in → **My availability** | *"A professor can no longer come on Sundays."* |
| Tap the whole Sunday column ("Can't") → Save | *"The professor marks it on their phone, and can also mark slots they'd rather avoid."* |
| Admin: Timetable → **Generate** | |
| By professor → that professor: no Sunday | *"Regenerated: nothing on Sunday for this professor, zero clashes, and only a couple of sessions moved."* |

(The admin can also fill this grid for a professor: Professors → Availability.)

## Clip 4: Jury case 3, an absence frees a room, another professor books it (~60 s)

| Screen | Voice-over |
| --- | --- |
| Prof Y: My week → tap tomorrow's class → **I'll be absent** | *"Prof Y is absent tomorrow. One tap."* |
| Phone (student of that group) → refresh → "Cancelled" | *"The students see it right away, no account needed."* |
| Prof Z: **Extra session** → pick a group → Find free slots | *"Prof Z needs a make-up session. The app finds when the professor, the students and a room are all free."* |
| Point at option 1: "Freed room" + reasons | *"Rooms freed by an absence come first, with the reasons: no gap for students, right size."* |
| **Book** → "Booked" | *"One tap to book."* |
| Phone (Prof Z's group) → "New session" | *"That group now sees the new session."* |
| Optional: a third window books the same option → "no longer available" + alternatives | *"Two professors on the same slot? First one wins, the other gets the next best options."* |

## Clip 5: Weak connection (~30 s)

| Screen | Voice-over |
| --- | --- |
| Phone: open the group page, then airplane mode, reopen the app | *"On campus the connection is often weak. The last timetable stays available."* |
| Show "Offline: showing the copy saved…" | |
| Prof (offline): declare an absence → banner "1 action waiting" | *"A professor's taps are kept…"* |
| Back online → "Sent: Absence…" | *"…and sent as soon as the signal returns."* |

## The 2-minute video (cut from the clips above)

| Time | Content |
| --- | --- |
| 0:00–0:20 | **Problem.** Photo or screenshot of a hand-made Excel timetable. *"Building the timetable takes days, clashes slip through, and when a professor is absent the room stays empty while someone else looks for one."* |
| 0:20–0:40 | **Approach.** *"A constraint solver, Google OR-Tools, guarantees zero clashes and optimises the gaps. A small language model running locally reads the department's messy files. No internet, no GPU."* |
| 0:40–1:05 | Clip 1, fast-forwarded: files → preview → Generate → 172 sessions, 0 clashes, 10 s. |
| 1:05–1:20 | Clip 2: room closed → only its sessions move. |
| 1:20–1:45 | Clip 4: absence → Cancelled → Extra session → Freed room → Book → New session. |
| 1:45–2:00 | Phone offline + numbers on screen: *"0 clashes, a break after 3 classes in a row, 470 MB of RAM, works offline. Ready to test in the department."* |
