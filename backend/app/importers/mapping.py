"""Match messy column headers to the expected fields, then clean each value.

Step 1: a synonym dictionary (French / English / Arabic) with fuzzy matching. Handles most files.
Step 2: columns still unmatched are passed to the column-mapper plug-in, if one is
        configured in .env (COLUMN_MAPPER_MODULE, see app/plugins.py).
The synonyms are in French, English and Arabic because those are the words used in the
department's files.
The admin always sees the result in a preview and can fix it before saving.
"""

import re
import unicodedata
from difflib import SequenceMatcher

YEAR = {"required": False, "syn": ["annee", "year", "annee d etude", "السنة"]}
SPECIALITY = {"required": False, "syn": ["specialite", "speciality", "filiere", "option", "التخصص"]}

FIELDS: dict[str, dict[str, dict]] = {
    "rooms": {
        "name": {
            "required": True,
            "syn": [
                "salle",
                "nom",
                "name",
                "room",
                "local",
                "designation",
                "nom salle",
                "القاعة",
            ],
        },
        "type": {
            "required": False,
            "syn": ["type", "nature", "categorie", "kind", "type salle", "النوع"],
        },
        "capacity": {
            "required": True,
            "syn": [
                "capacite",
                "capacity",
                "places",
                "nb places",
                "nombre de places",
                "effectif max",
                "السعة",
            ],
        },
    },
    "levels": {
        # The level's name, e.g. "L3 ISIL". Files often split it into a year column and a
        # speciality column: then the name is built from both (see clean_rows).
        "name": {
            "required": False,
            "syn": [
                "niveau",
                "level",
                "promotion",
                "parcours",
                "formation",
                "intitule de la formation",
                "المستوى",
            ],
        },
        "year": YEAR,
        "speciality": SPECIALITY,
        "headcount": {
            "required": True,
            "syn": [
                "effectif",
                "nombre",
                "nb etudiants",
                "headcount",
                "students",
                "etudiants",
                "nombre d etudiants",
                "العدد",
            ],
        },
    },
    "modules": {
        "level": {
            "required": False,
            "syn": [
                "niveau",
                "level",
                "promotion",
                "parcours",
                "formation",
                "المستوى",
            ],
        },
        "year": YEAR,
        "speciality": SPECIALITY,
        "name": {
            "required": True,
            "syn": [
                "module",
                "matiere",
                "intitule",
                "name",
                "course",
                "unite",
                "intitule du module",
                "المقياس",
            ],
        },
        "lecture": {
            "required": False,
            "syn": ["cours", "cm", "lecture", "vh cours", "cours semaine", "nb cours"],
        },
        "td": {"required": False, "syn": ["td", "vh td", "td semaine", "nb td"]},
        "tp": {"required": False, "syn": ["tp", "vh tp", "tp semaine", "nb tp"]},
    },
    "professors": {
        "name": {
            "required": True,
            "syn": [
                "enseignant",
                "nom",
                "professeur",
                "prof",
                "name",
                "teacher",
                "nom et prenom",
                "nom prenom",
                "الأستاذ",
            ],
        },
        "max_sessions": {
            "required": False,
            "syn": [
                "charge",
                "max seances",
                "seances max",
                "volume",
                "charge horaire",
                "max",
                "max sessions",
                "charge max",
            ],
        },
        # One wish per row (fiche de voeux): its order of preference and its level.
        "rank": {
            "required": False,
            "syn": ["ordre de preference", "ordre", "rang", "priorite", "preference", "rank", "choix"],
        },
        "level": {
            "required": False,
            "syn": ["formation", "niveau", "level", "promotion", "parcours"],
        },
        "modules": {
            "required": False,
            "syn": [
                "modules",
                "matieres",
                "module",
                "matiere",
                "modules enseignes",
                "courses",
                "voeux",
                "fiche de voeux",
            ],
        },
        "kinds": {
            "required": False,
            "syn": ["type enseignement", "nature", "kinds", "cours td tp"],
        },
    },
}


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode() or text
    t = re.sub(r"[^a-z0-9؀-ۿ]+", " ", t.lower())
    return " ".join(t.split())


def _score(header: str, syn: str) -> float:
    h, s = normalize(header), normalize(syn)
    if not h or not s:
        return 0.0
    if h == s:
        return 1.0
    words = h.split()
    if s in words or (" " in s and s in h):
        return 0.9
    if len(s) >= 4 and (h.startswith(s) or s in h):
        return 0.8
    return SequenceMatcher(None, h, s).ratio() * 0.9


def map_columns(kind: str, headers: list[str]) -> dict:
    if kind not in FIELDS:
        raise ValueError(f"Unknown import kind '{kind}'. Use one of {list(FIELDS)}")
    fields = FIELDS[kind]
    scored = []
    for field, spec in fields.items():
        for i, h in enumerate(headers):
            best = max(_score(h, s) for s in spec["syn"] + [field])
            if best >= 0.72:
                scored.append((best, field, i))
    scored.sort(reverse=True)
    mapping, used_cols = {}, set()
    for score, field, i in scored:
        if field in mapping or i in used_cols:
            continue
        mapping[field] = {
            "column": headers[i],
            "index": i,
            "confidence": round(score, 2),
            "method": "dictionary",
        }
        used_cols.add(i)

    unmapped = [h for i, h in enumerate(headers) if i not in used_cols and h]
    missing = [f for f in fields if f not in mapping]
    if unmapped and missing:
        try:  # optional AI step
            from .. import plugins

            llm_map, _ = plugins.load("COLUMN_MAPPER_MODULE", "map_columns")
            suggestions = (
                (llm_map(kind=kind, headers=unmapped, fields=missing) or {})
                if llm_map
                else {}
            )
            for field, header in suggestions.items():
                if field in missing and header in headers:
                    i = headers.index(header)
                    if i not in used_cols:
                        mapping[field] = {
                            "column": header,
                            "index": i,
                            "confidence": 0.6,
                            "method": "llm",
                        }
                        used_cols.add(i)
        except Exception:  # noqa: BLE001  (not installed, model missing, bad answer...)
            pass
    return {
        "mapping": mapping,
        "unmapped_columns": [
            h for i, h in enumerate(headers) if i not in used_cols and h
        ],
        "missing_fields": [f for f in fields if f not in mapping],
        "missing_required": [
            f for f, spec in fields.items() if spec["required"] and f not in mapping
        ],
    }


# ---------------------------------------------------------------- value cleaning


def to_int(v: str) -> int | None:
    m = re.search(r"\d+", v or "")
    return int(m.group()) if m else None


def to_sessions(v: str) -> int | None:
    """'2' -> 2 sessions. '3h00' / '3h' / '4h30' -> hours / 1h30. '' -> 0."""
    v = (v or "").strip().lower().replace(",", ".")
    if not v or v in {"-", "/", "0"}:
        return 0
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*h\s*(\d{1,2})?(?:\s*min)?", v)
    if m:
        hours = float(m.group(1)) + (int(m.group(2)) / 60 if m.group(2) else 0)
        return max(0, round(hours / 1.5))
    m = re.fullmatch(r"(\d+)\s*:\s*(\d{2})", v)
    if m:
        return max(0, round((int(m.group(1)) + int(m.group(2)) / 60) / 1.5))
    try:
        return max(0, round(float(v)))
    except ValueError:
        return None


def room_type(v: str) -> str:
    t = normalize(v or "")
    if "amphi" in t:
        return "amphi"
    if any(k in t for k in ("tp", "lab", "info", "machine", "atelier")):
        return "lab"
    return "td"


def kinds_from(v: str) -> str:
    t = normalize(v or "")
    if not t:
        return "lecture,td,tp"
    out = []
    if "cours" in t or "cm" in t.split() or "lecture" in t:
        out.append("lecture")
    if "td" in t.split():
        out.append("td")
    if "tp" in t.split():
        out.append("tp")
    return ",".join(out) or "lecture,td,tp"


def level_name(raw: dict, field: str) -> str:
    """'L3' + 'ISIL' -> 'L3 ISIL' when the file splits the level into two columns."""
    year, spec = (raw.get("year") or "").strip(), (raw.get("speciality") or "").strip()
    if year and spec:
        return year if normalize(spec) in normalize(year) else f"{year} {spec}"
    return (raw.get(field) or year or spec or "").strip()


def is_hours(header: str) -> bool:
    """'Charge max (h/sem)', 'Volume horaire'... : the value is in hours, not sessions."""
    h = normalize(header)
    return bool(re.search(r"\bh\b|heure|horaire|hours", h))


def clean_rows(
    kind: str, headers: list[str], rows: list[list[str]], mapping: dict, session_hours: float = 1.5
) -> tuple[list[dict], list[str]]:
    """Apply the mapping and clean every value. Returns (rows as dicts, warnings).
    `session_hours` (length of one time slot) converts a load given in hours into sessions."""
    out, warnings = [], []
    # Many lists split "Nom" and "Prénom" so glue the first name back onto the name.
    first_name_col = next(
        (
            i
            for i, h in enumerate(headers)
            if normalize(h) in {"prenom", "first name", "firstname"}
            and i not in {m["index"] for m in mapping.values()}
        ),
        None,
    )
    for n, r in enumerate(rows, start=1):
        raw = {
            f: r[m["index"]] if m["index"] < len(r) else "" for f, m in mapping.items()
        }
        row: dict = {}
        if kind == "rooms":
            row["name"] = raw.get("name", "")
            row["type"] = room_type(raw.get("type", "") or raw.get("name", ""))
            row["capacity"] = to_int(raw.get("capacity", ""))
            if row["capacity"] is None:
                warnings.append(f"row {n}: capacity missing for room '{row['name']}'")
        elif kind == "levels":
            row["name"] = level_name(raw, "name")
            row["headcount"] = to_int(raw.get("headcount", ""))
            if row["headcount"] is None:
                warnings.append(f"row {n}: headcount missing for '{row['name']}'")
        elif kind == "modules":
            row["level"] = level_name(raw, "level")
            row["name"] = raw.get("name", "")
            for f in ("lecture", "td", "tp"):
                val = to_sessions(raw.get(f, ""))
                if val is None:
                    warnings.append(f"row {n}: can't read {f} value '{raw.get(f)}'")
                    val = 0
                row[f] = val
        elif kind == "professors":
            row["name"] = raw.get("name", "")
            if (
                first_name_col is not None
                and first_name_col < len(r)
                and r[first_name_col]
            ):
                row["name"] = f"{r[first_name_col]} {row['name']}".strip()
            row["max_sessions"] = to_int(
                raw.get("max_sessions", "")
            )  # empty = department default
            if row["max_sessions"] and is_hours(mapping["max_sessions"]["column"]):
                row["max_sessions"] = max(1, round(row["max_sessions"] / session_hours))
            row["rank"] = to_int(raw.get("rank", ""))
            row["level"] = (raw.get("level") or "").strip()
            mods = re.split(r"[;,/\n]+", raw.get("modules", "") or "")
            row["modules"] = [m.strip() for m in mods if m.strip()]
            row["kinds"] = kinds_from(raw.get("kinds", ""))
        if not row.get("name"):
            continue  # skip blank / total lines
        out.append(row)
    return out, warnings
