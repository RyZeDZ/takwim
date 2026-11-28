"""Start the API on a hosting panel (e.g. a Pterodactyl Python server).

    python backend/serve.py

Listens on the port given by the panel (SERVER_PORT), or PORT, or 8000. Runs from the backend
folder, so `.env` and `timetable.db` are found there, and uses Algeria's time zone (dates are
compared with "today").
"""
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.chdir(HERE)
sys.path.insert(0, str(HERE))
os.environ.setdefault("TZ", "Africa/Algiers")
time.tzset()

import uvicorn  # noqa: E402

if __name__ == "__main__":
    port = int(os.getenv("SERVER_PORT") or os.getenv("PORT") or 8000)
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, proxy_headers=True,
                forwarded_allow_ips="*")
