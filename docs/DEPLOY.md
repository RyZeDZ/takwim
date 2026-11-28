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

The database is the file `backend/timetable.db`: back it up by copying it.
