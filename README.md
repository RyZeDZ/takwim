# Smart timetables for the department

**The problem.** In our computer-science department, the weekly timetable is built by hand in
Excel. It takes days, clashes slip through (two groups in one room, a professor in two places),
and it breaks every time something changes: a room closes for repairs, a professor can no
longer come on Sundays. During the semester, when a professor is absent, the room stays
empty while another professor is looking for a room to catch up, and students find out about
cancelled classes at the door. On top of that, the connection on campus is often weak.

**What the app does.**

- **The administration** uploads the files it already has (Excel, CSV or PDF lists of levels,
  rooms, modules and professors' wish lists), checks a preview, and clicks **Generate**: the
  groups are formed from the number of students and a full weekly timetable is built in about
  ten seconds, with **zero clashes**. When something changes, it clicks again: only what must
  move moves. Timetables export to Excel and PDF in the usual layout.
- **Professors** see their week, tap a class to say "I'll be absent" (the room is freed at
  once), mark the slots they can't teach, and book an extra session: the app proposes the best
  times when they, their students and a room are all free, preferring rooms freed by an absence.
  First to book wins.
- **Students** need no account: they open their group's page (link or QR code) and see
  *Cancelled* and *New session* labels. The last timetable stays readable with no connection,
  and a professor's taps made offline are sent when the signal returns.

## The AI inside, and why this one

1. **A constraint solver (Google OR-Tools CP-SAT)** builds the timetable. Strict rules can never
   be broken: no double booking, the right type of room with enough seats, only professors who
   teach that module, never in a slot they marked "I can't", within their weekly and daily
   limits. Preferences are optimised: few empty gaps in a student's day, professors' first
   choices and "I'd rather not" slots, few changes after an edit. A chatbot cannot guarantee
   zero clashes for hundreds of students; a solver can, and every result is re-checked before
   it is saved.
2. **A small language model running on the computer itself (Qwen2.5 1.5B, through llama.cpp)**
   helps read messy files: when a column is called "Cap. accueil" or "Nbre de places assises",
   it suggests which field it is. The administrator always confirms in the preview.

## What we measured (ordinary laptop, no graphics card)

Synthetic department: 6 levels, 24 groups, 20 professors, 21 rooms, **172 sessions per week**.
Laptop: AMD Ryzen 7 6800H, 16 GB RAM; the solver uses 4 CPU threads.

| | Built-in quick method | AI solver (CP-SAT) |
| --- | --- | --- |
| Sessions placed | 172 / 172 | 172 / 172 |
| Clashes | 0 | 0 |
| Empty slots between classes that are not a needed break, per group per week | 0.61 | **0.39 to 0.50** |
| Classes beyond 3 in a row with no break (whole department, per week) | 11 | **6 to 9** |
| Days with a single class (students come in for one session) | 6 | **0 to 3** |
| TD / TP placed before its lecture on the same day | 5 | **1 to 2** |
| Sessions moved when a busy room closes | only the ones in that room | only the ones in that room |
| Time to generate | 0.02 s | 10 s (time limit, adjustable) |

AI solver ranges are over several runs. After 3 classes in a row the solver tries to leave a
free slot (the admin sets the number in Settings).

- **Messy headers:** on 10 test files written like department files (40 columns to recognise),
  the dictionary alone gets **68 %** right; with the language model, **88 %** (1 wrong
  suggestion, caught in the preview), about 1.3 s per file.
- **Memory:** the server peaks at about 460 MB while generating; about 1.9 GB once the
  language model is loaded for an import. **Model size on disk:** 1.1 GB. No internet needed.
- Extra-session search: under a second. All 47 automated tests pass.

## Try it

```bash
# Backend (Python 3.11+)
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # choose ADMIN_USERNAME / ADMIN_PASSWORD; DEMO_MODE=1 for the demo
uvicorn app.main:app

# Web app (Node 20+), in another terminal
cd frontend && npm install && cp .env.example .env && npm run dev
```

Open http://localhost:5173, log in as the administrator, click **Load demo department**, then
**Generate**. The three demo cases (a room closes, a professor can't teach on Sundays anymore,
a professor is absent and another books the freed room) also run on their own with
`python backend/scripts/demo_cases.py`.

## Limits (stated, not hidden)

- An extra session is one time slot; no double-length bookings.
- The solver stops at its time limit: the timetable is always valid, but not proven to be the
  best possible one.
- A practical class needs a lab at least as large as the group.
- Scanned paper (photos) is not read; PDFs exported from Word or Excel are.
- All data in the demo is synthetic: no real names or personal data.
