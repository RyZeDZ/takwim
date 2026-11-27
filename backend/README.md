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
