"""Optional AI plug-ins, chosen in .env (no code change in the backend):

    SOLVER_MODULE=ai.solver               -> must define  solve(data) -> result
    COLUMN_MAPPER_MODULE=ai.column_mapper -> must define  map_columns(kind, headers, fields) -> dict

The repository root (the folder above backend/) is added to the import path, so modules
from the repository's ai/ folder can be used directly.
"""
import importlib
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load(env_var: str, function: str):
    """Returns (function, module_name), or (None, None) when the env variable is empty.
    Raises ImportError / AttributeError with a clear message if the plug-in is broken."""
    name = os.getenv(env_var, "").strip()
    if not name:
        return None, None
    if str(REPO_ROOT) not in sys.path:
        sys.path.append(str(REPO_ROOT))
    module = importlib.import_module(name)
    fn = getattr(module, function, None)
    if not callable(fn):
        raise AttributeError(f"{name} has no function '{function}'")
    return fn, name
