"""Server settings, read from environment variables or from the .env file next to this folder.

Only technical settings live here (database, admin account, security). The department's
rules (days, time slots, group sizes...) are stored in the database and edited by the admin:
see app/rules.py.
"""

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load_env_file(path: Path = ENV_FILE) -> None:
    """Minimal .env reader: KEY=VALUE lines, # comments. Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()


class Settings:
    app_name = os.getenv("APP_NAME", "Timetable API")
    database_url = os.getenv("DATABASE_URL", "sqlite:///./timetable.db")

    # The first admin account, created on first start. No default: must be set in .env.
    admin_username = os.getenv("ADMIN_USERNAME", "").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "")

    # How long someone stays logged in before having to log in again.
    login_expires_hours = int(os.getenv("LOGIN_EXPIRES_HOURS", "72"))

    # Which websites may call this API. "*" = any.
    cors_origins = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
    ]

    # Lets the admin load the synthetic demo department (only into an empty database).
    demo_mode = os.getenv("DEMO_MODE", "0") == "1"


settings = Settings()
