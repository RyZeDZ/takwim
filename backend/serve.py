"""Start the API on a hosting panel (e.g. a Pterodactyl Python server).

    python backend/serve.py

Listens on the port given by the panel (SERVER_PORT), or PORT, or 8000. Runs from the backend
folder, so `.env` and `timetable.db` are found there, and uses Algeria's time zone (dates are
compared with "today"). When the language model is turned on (COLUMN_MAPPER_MODULE) and its
file is missing, it is downloaded first (about 1 GB, once).
"""
import os
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.chdir(HERE)
sys.path.insert(0, str(HERE))
os.environ.setdefault("TZ", "Africa/Algiers")
time.tzset()

from app.config import load_env_file  # noqa: E402

load_env_file()

MODEL_URL = ("https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
             "qwen2.5-1.5b-instruct-q4_k_m.gguf")


def download_model() -> None:
    """Fetch the language model once, if it is turned on and not there yet."""
    if not os.getenv("COLUMN_MAPPER_MODULE"):
        return
    target = Path(os.getenv("COLUMN_MAPPER_MODEL") or HERE.parent / "models" / MODEL_URL.rsplit("/", 1)[1])
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(".part")  # renamed only when complete
    print(f"Downloading the language model to {target} (about 1 GB, once)...", flush=True)
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=60) as r, open(part, "wb") as f:
            total, done, shown = int(r.headers.get("Content-Length") or 0), 0, -10
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                pct = done * 100 // total if total else 0
                if pct >= shown + 10:
                    print(f"  {pct} % ({done >> 20} MB)", flush=True)
                    shown = pct
        part.rename(target)
        print("Language model ready.", flush=True)
    except Exception as e:  # noqa: BLE001  (the API still starts: imports use the dictionary)
        part.unlink(missing_ok=True)
        print(f"Model download failed ({e}); imports will use the dictionary only.", flush=True)


if __name__ == "__main__":
    import uvicorn

    download_model()
    port = int(os.getenv("SERVER_PORT") or os.getenv("PORT") or 8000)
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, proxy_headers=True,
                forwarded_allow_ips="*")
