import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp()
# Test-only settings (they win over any .env file).
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["ADMIN_USERNAME"] = "test-admin"
os.environ["ADMIN_PASSWORD"] = "test-password-123"
os.environ["DEMO_MODE"] = "1"
os.environ["SOLVER_MODULE"] = ""
os.environ["COLUMN_MAPPER_MODULE"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import ensure_admin  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        ensure_admin(db)
    with TestClient(app) as c:
        yield c


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin(client):
    r = client.post("/auth/login", json={"username": "test-admin", "password": "test-password-123"})
    assert r.status_code == 200, r.text
    return auth(r.json()["token"])


@pytest.fixture()
def demo(client, admin):
    """Seeded demo department with a generated timetable (groups are built by 'generate')."""
    seeded = client.post("/admin/demo/seed", headers=admin)
    assert seeded.status_code == 200, seeded.text
    gen = client.post("/admin/timetable/generate", headers=admin)
    assert gen.status_code == 200, gen.text
    assert gen.json()["saved"], gen.json()
    return seeded.json()


def login_prof(client, creds: dict) -> dict:
    r = client.post("/auth/login", json={"username": creds["username"],
                                         "password": creds["password"]})
    assert r.status_code == 200, r.text
    return auth(r.json()["token"])


def next_date_for_day(day: int, start_offset: int = 1) -> date:
    """First date from tomorrow (or later) whose timetable day index is `day`
    (with the default rules: 0 = Sunday ... 4 = Thursday, 5 = Friday is not a working day)."""
    names = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    d = date.today() + timedelta(days=start_offset)
    while weekdays[d.weekday()] != names[day]:
        d += timedelta(days=1)
    return d
