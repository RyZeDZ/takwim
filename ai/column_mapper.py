"""Column mapper with a small local language model (llama.cpp, CPU only, no internet).

Plugged into the backend with COLUMN_MAPPER_MODULE=ai.column_mapper (backend/.env).
The backend first matches headers with its synonym dictionary; only the columns it could
not match are sent here, e.g. "Nbre de places assises" or "Cap. accueil" for the capacity.

The model reads the field descriptions and the unmatched headers and answers in JSON
{field: header}. The answer is constrained to that JSON shape, and every suggestion is
checked (the header must exist, one header per field). The admin still sees the result in
the import preview, marked "AI suggestion", and can change it.

Model: Qwen2.5-1.5B-Instruct, quantised to 4 bits (GGUF, about 1 GB on disk), open licence.
Settings (environment variables, optional):
  COLUMN_MAPPER_MODEL    path of the .gguf file (default: models/qwen2.5-1.5b-instruct-q4_k_m.gguf)
  COLUMN_MAPPER_THREADS  CPU threads (default 4)
"""
import json
import os
from pathlib import Path

DEFAULT_MODEL = Path(__file__).resolve().parents[1] / "models" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"

# What each field means, in plain words, for the model.
DESCRIPTIONS = {
    "rooms": {
        "name": "the room's name or number",
        "type": "the kind of room (lecture hall, classroom, computer lab)",
        "capacity": "how many seats / students the room holds",
    },
    "levels": {
        "name": "the full name of the level or study programme",
        "year": "the study year (L1, L2, L3, M1, M2)",
        "speciality": "the speciality / branch (e.g. ISIL, SI, AI)",
        "headcount": "the number of students enrolled",
    },
    "modules": {
        "name": "the module / course / subject name",
        "level": "the level or programme it belongs to",
        "year": "the study year (L1, L2, L3, M1, M2)",
        "speciality": "the speciality / branch",
        "lecture": "number of lecture sessions (cours) per week",
        "td": "number of tutorial (TD) sessions per week",
        "tp": "number of lab (TP) sessions per week",
    },
    "professors": {
        "name": "the teacher's full name",
        "max_sessions": "the teacher's maximum teaching load per week",
        "modules": "the module(s) the teacher wants to teach",
        "kinds": "which kinds of sessions: lecture (cours), TD, TP",
        "rank": "the order of preference of this wish (1 = first choice)",
        "level": "the level or programme of the wished module",
    },
}

_llm = None


def _model():
    """Load the model once (about 1 s), then keep it in memory."""
    global _llm
    if _llm is None:
        from llama_cpp import Llama

        path = os.getenv("COLUMN_MAPPER_MODEL") or str(DEFAULT_MODEL)
        if not Path(path).exists():
            raise FileNotFoundError(f"language model not found: {path}")
        _llm = Llama(model_path=path, n_ctx=2048, n_threads=int(os.getenv("COLUMN_MAPPER_THREADS", "4")),
                     verbose=False)
    return _llm


def map_columns(kind: str, headers: list[str], fields: list[str]) -> dict:
    """Suggest {field: header} for the fields the dictionary could not match."""
    described = {f: DESCRIPTIONS.get(kind, {}).get(f, f) for f in fields}
    if not headers or not described:
        return {}
    prompt = (
        f"A university department uploaded a table of {kind}. Some column headers were not "
        "recognised. Match each field below to the column header that contains it, or null "
        "if no header fits. Headers may be in French, English or Arabic, abbreviated or misspelt.\n\n"
        "Fields:\n" + "\n".join(f"- {f}: {d}" for f, d in described.items()) +
        "\n\nColumn headers:\n" + "\n".join(f"- {h}" for h in headers) +
        "\n\nAnswer with a JSON object whose keys are the fields and whose values are exact headers or null."
    )
    schema = {
        "type": "object",
        "properties": {f: {"anyOf": [{"type": "string", "enum": headers}, {"type": "null"}]} for f in described},
        "required": list(described),
    }
    out = _model().create_chat_completion(
        messages=[{"role": "system", "content": "You map spreadsheet columns to data fields. Answer in JSON only."},
                  {"role": "user", "content": prompt}],
        response_format={"type": "json_object", "schema": schema},
        temperature=0,
        max_tokens=200,
    )
    answer = json.loads(out["choices"][0]["message"]["content"])
    result, used = {}, set()
    for field, header in answer.items():
        if field in described and header in headers and header not in used:
            result[field] = header
            used.add(header)
    return result
