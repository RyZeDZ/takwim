"""Import the department's existing files. Two steps, so nothing is saved blindly:

1. POST /admin/import/preview  (file + kind)  -> detected columns, cleaned rows, warnings
2. POST /admin/import/commit   (kind + rows, possibly fixed by the admin) -> saved
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session as DB

from ..auth import log, require_admin
from ..db import get_db
from ..importers.mapping import FIELDS, clean_rows, map_columns
from ..importers.readers import ImportError_, read_table
from ..schemas import ImportCommitIn
from ..services.catalog import commit_rows

router = APIRouter(
    prefix="/admin/import", tags=["import"], dependencies=[Depends(require_admin)]
)

MAX_BYTES = 10 * 1024 * 1024


@router.get("/kinds")
def kinds():
    """What can be imported, and the fields expected in each file."""
    return {
        k: {
            f: {"required": spec["required"], "examples": spec["syn"][:4]}
            for f, spec in fields.items()
        }
        for k, fields in FIELDS.items()
    }


@router.post("/preview")
async def preview(
    kind: str = Form(...),
    file: UploadFile = File(...),
    column_overrides: str | None = Form(None),
):
    """`column_overrides` (optional) is JSON like {"capacity": "Nb places"} when the admin
    corrects a column the automatic matching got wrong."""
    import json

    if kind not in FIELDS:
        raise HTTPException(422, f"kind must be one of {list(FIELDS)}")
    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "File too large (10 MB max)")
    try:
        headers, rows = read_table(file.filename or "", content)
    except ImportError_ as e:
        raise HTTPException(422, str(e)) from e
    result = map_columns(kind, headers)
    if column_overrides:
        try:
            overrides = json.loads(column_overrides)
        except json.JSONDecodeError as e:
            raise HTTPException(422, "column_overrides must be JSON") from e
        for field, header in overrides.items():
            if field in FIELDS[kind] and header in headers:
                result["mapping"][field] = {
                    "column": header,
                    "index": headers.index(header),
                    "confidence": 1.0,
                    "method": "admin",
                }
        mapped_cols = {m["index"] for m in result["mapping"].values()}
        result["unmapped_columns"] = [
            h for i, h in enumerate(headers) if i not in mapped_cols and h
        ]
        result["missing_fields"] = [
            f for f in FIELDS[kind] if f not in result["mapping"]
        ]
        result["missing_required"] = [
            f
            for f, sp in FIELDS[kind].items()
            if sp["required"] and f not in result["mapping"]
        ]
    cleaned, warnings = clean_rows(kind, headers, rows, result["mapping"])
    return {
        "kind": kind,
        "filename": file.filename,
        "columns": headers,
        "mapping": {
            f: {k: v for k, v in m.items() if k != "index"}
            for f, m in result["mapping"].items()
        },
        "unmapped_columns": result["unmapped_columns"],
        "missing_fields": result["missing_fields"],
        "missing_required": result["missing_required"],
        "rows": cleaned,
        "row_count": len(cleaned),
        "warnings": warnings,
        "ready": not result["missing_required"],
    }


@router.post("/commit")
def commit(body: ImportCommitIn, db: DB = Depends(get_db), user=Depends(require_admin)):
    result = commit_rows(db, body.kind, body.rows)
    log(db, user, "import", f"{body.kind}: +{result['created']} ~{result['updated']}")
    db.commit()
    return result
