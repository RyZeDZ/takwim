# Frontend

React + Vite web app, phone-first and installable (PWA). Three spaces:

- **Students** (no account): pick a group, see the live week with *Cancelled* / *New session*
  badges, download PDF / Excel, share the page with a QR code, find a free room.
- **Professors**: my week (tap a class to declare an absence), extra session (ranked free slots,
  book in one tap; if someone was faster, the next best options are shown), availability grid
  ("I can't" / "I'd rather not"), my absences and bookings.
- **Admin**: dashboard and *Generate*, timetable by group / professor / room (move a session,
  mark an absence), import wizard (preview, fix columns, save), levels, modules, professors
  (wish-list order, availability, passwords), rooms (close / reopen), settings, activity log.

## Run it

```bash
cd frontend
npm install
cp .env.example .env     # VITE_API_URL = address of the backend
npm run dev              # http://localhost:5173
npm run build            # production files in dist/ (serve them with any web server)
```

The backend must allow this address in `CORS_ORIGINS` (`*` by default).

## How it works offline

- `src/api/client.ts` is the only file that calls the backend. Every GET response is saved in
  the browser, so the last timetable opened is still shown without a connection.
- An absence or an extra session tapped offline is queued and sent when the connection returns
  (the backend ignores duplicates, so a replay is always safe).
- The service worker (vite-plugin-pwa) caches the app itself, so it opens with no network.

Days and time slots are never hard-coded: every grid is drawn from `GET /public/config`.

## Languages, theme

- Every text on screen is written in English inside `t('...')` (`src/lib/i18n.tsx`); the French
  and Arabic versions are in `src/lib/translations.ts`, keyed by the English text. A missing
  translation shows the English text. Placeholders: `t('{n} rooms', { n })`.
- Arabic switches the page to right-to-left; layout uses logical CSS properties
  (`margin-inline-start`...). Times and ranges stay left-to-right (`ltr()` in `src/lib/dates.ts`).
- Dark mode follows the device, or the switch in the header (`data-theme` on `<html>`).
