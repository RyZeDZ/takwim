# Hosting the app on a server

Two parts: the API (Python) and the web app (static files). Example with
`app.example.com` for the web app and `api.example.com` for the API.

## 1. API

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install llama-cpp-python                 # optional: local language model for imports
cp .env.example .env
```

In `backend/.env`:

- `ADMIN_USERNAME`, `ADMIN_PASSWORD` (8+ characters): the administrator's login.
- `CORS_ORIGINS=https://app.example.com`
- `DEMO_MODE=1` to allow "Load demo department" (only works on an empty database).
- `SOLVER_MODULE=ai.solver`, and `SOLVER_TIME_LIMIT` / `SOLVER_WORKERS` for the solver.
- `COLUMN_MAPPER_MODULE=ai.column_mapper` with the model in `models/` (see `models/README.md`).

Run it with the server's timezone set to Algeria (dates are compared with "today"):

```bash
TZ=Africa/Algiers uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Keep it running with systemd (or `tmux`), and put a reverse proxy with HTTPS in front of it.

## 2. Web app

```bash
cd frontend
echo "VITE_API_URL=https://api.example.com" > .env
npm install && npm run build      # files in frontend/dist/
```

Serve `frontend/dist/` over HTTPS (needed for the offline mode). Every unknown path must
return `index.html`, so links like `/g/12` (QR codes) work. nginx example:

```nginx
server {
  server_name app.example.com;
  root /path/to/frontend/dist;
  location / { try_files $uri /index.html; }
}
server {
  server_name api.example.com;
  location / { proxy_pass http://127.0.0.1:8000; proxy_read_timeout 120s; }
}
```

### Only one subdomain? Put the API under `/api`

Build with `VITE_API_URL=https://app.example.com/api`, set `CORS_ORIGINS=https://app.example.com`,
and use one server block:

```nginx
server {
  server_name app.example.com;
  root /path/to/frontend/dist;
  location /api/ { proxy_pass http://127.0.0.1:8000/; proxy_read_timeout 120s; }
  location / { try_files $uri /index.html; }
}
```

The trailing `/` after `8000` removes `/api` before the request reaches the API.

## 3. Before the jury tests it

- Run a single API process (no `--workers`): the database is one SQLite file.
- Memory: about 0.5 GB while generating, plus about 1.9 GB when the language model is loaded
  for an import. On a server with less than 3 GB of RAM, leave `COLUMN_MAPPER_MODULE` empty
  (imports then use the dictionary only).
- Set up the demo once (Load demo department, Generate), copy the professor logins, then make a
  copy of `backend/timetable.db`. Between two jury sessions, stop the API, put the copy back and
  start it again to return to a clean state.

The database is the file `backend/timetable.db`: back it up by copying it.
