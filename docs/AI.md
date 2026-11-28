# How the AI works

Two pieces of AI, both running on the server itself (no internet, no GPU).

## 1. The timetable solver: `ai/solver.py` (constraint programming, Google OR-Tools CP-SAT)

**What goes in.** The backend (`backend/app/services/solver_adapter.py`) turns the database into
plain lists: days and time slots, open rooms, groups (section → TD groups → TP subgroups),
professors (weekly maximum, "can't" slots, "rather not" slots), who can teach what (module,
lecture/TD/TP, wish-list rank), and one **requirement** per weekly session to place
(e.g. "Algorithms 1, TD, group L1 CS - G3", twice if it is twice a week). It also passes the
current timetable, so a re-solve can keep sessions where they are.

**The model.** For every requirement the solver has yes/no choices:

- `y[bundle, prof]`: which professor teaches this module/kind for this group (one per bundle,
  so a group keeps the same TD teacher all semester);
- `w[req, prof, time]`: this session happens at this time with this professor;
- `x[req, time, room class]`: and in this kind of room. Rooms with the same type and seats are
  interchangeable (12 classrooms of 40 seats = one class with 12 places), which keeps the
  model small; the actual room is picked afterwards, keeping the previous room when possible.

**Hard rules (constraints: a solution that breaks one does not exist for the solver).**
Each session is placed exactly once (or explicitly left out, see below); a professor gives one
session at a time, never in a "can't" slot, at most `max_sessions` per week and
`max_sessions_per_day_per_professor` per day; a room class never holds more sessions than it has
rooms; a group never has two sessions at once, and a section's lecture blocks all its groups;
at most `max_sessions_per_day_per_group` per day; right room type, enough seats.

**Soft goals (the objective: a weighted sum of penalties the solver makes as small as it can).**
Leaving a session out (1000 — so it only happens when truly impossible, with the reason
reported); moving a session compared with the current timetable (20); each empty slot between
two classes in a group's day (6); a "rather not" slot (5); each step down a professor's wish
list (3); the same module twice the same day for a group (3); the last slot of the day (1);
a second-choice room type (1); each class beyond `max_sessions_in_a_row` back to back, for a
group or a professor (8, above the gap weight so that 2 + break + 2 beats 4 in a row); a day with
a single class (4); a day that does not start in the first slot (2); a TD / TP before its lecture
on the same day (2). The weights are at the top of `ai/solver.py`.

**The search.** It starts from the built-in greedy solver's timetable (valid, found in 0.02 s)
and improves it for `SOLVER_TIME_LIMIT` seconds (10 by default) on `SOLVER_WORKERS` threads (4).
Safety net: if the search ends with fewer sessions placed than the greedy start, the greedy
timetable is used. Then the backend re-checks every hard rule (`find_conflicts`) and refuses to
save anything invalid; if the solver crashes, the built-in one runs and a warning is shown.

**Measured** (`ai/benchmark.py`, demo department, 172 sessions, greedy → CP-SAT over several
runs): 0 clashes for both; empty slots that are not a needed break, per group per week 0.61 →
0.39–0.50; classes beyond 3 in a row 11 → 6–9; one-class days 6 → 0–3; TD / TP before its
lecture 5 → 1–2; after closing a busy room, only the sessions that were in it move (plus one or
two); ~10 s; server peak ~470 MB. A break counts as one when the classes on both sides add up to
more than the limit. Given 30 s instead of 10, CP-SAT gets down to about 1 class beyond 3 in a row.

**Why not a chatbot / neural network?** They cannot guarantee zero clashes; a solver proves every
rule holds, and can explain why a session could not be placed.

## 2. The column reader: `ai/column_mapper.py` (small local language model)

Department files have headers like "Nbre de places assises" or "Cap. accueil". The backend
first uses a synonym dictionary (French/English/Arabic, fuzzy matching:
`backend/app/importers/mapping.py`). Only the columns it can't match go to the model:
**Qwen2.5-1.5B-Instruct**, 4-bit, 1.1 GB, run by llama.cpp on the CPU. The model gets the field
descriptions and the headers, and must answer in a fixed JSON shape (it can only pick an
existing header or null). Suggestions show as "AI suggestion" in the preview; the admin confirms.

**Measured** (`ai/import_benchmark.py`, 10 messy header sets, 40 columns): dictionary alone 68 %,
with the model 88 % (1 wrong, shown in the preview), ~1.3 s per file, ~1.9 GB RAM while loaded.

## 3. The extra-session finder (rules, not machine learning): `backend/app/services/live.py`

For each date and slot in the range: professor free, group (and its section/subgroups) free,
room free and big enough. Each option gets a score: +15 reuses a room freed by an absence, +10
no gap for students, −4 per day later, −40 if the group already has its daily maximum, −10 if
students would come in only for it, minus wasted seats. The reasons are shown to the professor.
"First claim wins" is enforced by the database (one booking per room, date and slot).
