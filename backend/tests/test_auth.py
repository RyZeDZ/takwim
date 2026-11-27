import pytest

from conftest import auth


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_login_logout(client, admin):
    assert client.post("/auth/login", json={"username": "admin", "password": "nope"}).status_code == 401
    assert client.post("/auth/login", json={"username": "ghost", "password": "x"}).status_code == 401
    me = client.get("/auth/me", headers=admin)
    assert me.status_code == 200 and me.json()["role"] == "admin"
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers=auth("garbage")).status_code == 401
    assert client.post("/auth/logout", headers=admin).status_code == 200
    assert client.get("/auth/me", headers=admin).status_code == 401  # token is dead


def test_admin_must_come_from_env(client, monkeypatch):
    """No hard-coded admin: with an empty database and no .env values, startup refuses clearly."""
    from app.auth import MissingAdminConfig, ensure_admin
    from app.config import settings
    from app.db import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        db.query(User).delete()
        db.commit()
        monkeypatch.setattr(settings, "admin_password", "")
        with pytest.raises(MissingAdminConfig):
            ensure_admin(db)
        monkeypatch.setattr(settings, "admin_password", "short")
        with pytest.raises(MissingAdminConfig):
            ensure_admin(db)


def test_tokens_are_not_stored_in_clear(client, admin):
    from app.db import SessionLocal
    from app.models import AuthToken

    token = admin["Authorization"].split()[1]
    with SessionLocal() as db:
        stored = [t.token_hash for t in db.query(AuthToken)]
    assert token not in stored and len(stored[0]) == 64
