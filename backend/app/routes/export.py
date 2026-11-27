from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session as DB

from ..db import get_db
from ..exporters.timetable_export import to_excel, to_pdf

router = APIRouter(prefix="/export", tags=["export"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _ids(ids: str | None) -> list[int] | None:
    return [int(x) for x in ids.split(",") if x.strip()] if ids else None


@router.get("/excel")
def excel(scope: Literal["group", "prof", "room"] = "group",
          ids: str | None = Query(None, description="comma-separated ids; empty = all"),
          db: DB = Depends(get_db)):
    """Public: students can download their group's timetable without logging in."""
    data = to_excel(db, scope, _ids(ids))
    return Response(data, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="timetable_{scope}.xlsx"'})


@router.get("/pdf")
def pdf(scope: Literal["group", "prof", "room"] = "group",
        ids: str | None = Query(None, description="comma-separated ids; empty = all"),
        db: DB = Depends(get_db)):
    data = to_pdf(db, scope, _ids(ids))
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="timetable_{scope}.pdf"'})
