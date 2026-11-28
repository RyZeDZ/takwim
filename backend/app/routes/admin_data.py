"""Admin: rooms, levels, modules and professors (create / list / edit / delete)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DB

from ..auth import hash_password, new_password, require_admin
from ..db import get_db
from ..models import Level, Module, Professor, Room, Teaching, Unavailability, User
from ..schemas import (
    AvailabilityIn,
    LevelIn,
    LevelOut,
    ModuleIn,
    ModuleOut,
    ProfessorCreated,
    ProfessorIn,
    ProfessorOut,
    RoomIn,
    RoomOut,
    RoomPatch,
)
from ..services.catalog import (
    availability_view,
    create_professor,
    professor_view,
    save_availability,
    set_teaching,
)
from .common import commit_or_409, get_or_404

router = APIRouter(prefix="/admin", tags=["admin: data"], dependencies=[Depends(require_admin)])


# ------------------------------------------------------------------ rooms
@router.get("/rooms", response_model=list[RoomOut])
def list_rooms(db: DB = Depends(get_db)):
    return db.scalars(select(Room).order_by(Room.name)).all()


@router.post("/rooms", response_model=RoomOut, status_code=201)
def create_room(body: RoomIn, db: DB = Depends(get_db)):
    r = Room(**body.model_dump())
    db.add(r)
    commit_or_409(db)
    return r


@router.patch("/rooms/{room_id}", response_model=RoomOut)
def update_room(room_id: int, body: RoomPatch, db: DB = Depends(get_db)):
    """Use {"active": false} when a room is closed (repairs...), then regenerate."""
    r = get_or_404(db, Room, room_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(r, k, v)
    commit_or_409(db)
    return r


@router.delete("/rooms/{room_id}")
def delete_room(room_id: int, db: DB = Depends(get_db)):
    db.delete(get_or_404(db, Room, room_id))
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ levels
@router.get("/levels", response_model=list[LevelOut])
def list_levels(db: DB = Depends(get_db)):
    return db.scalars(select(Level).order_by(Level.name)).all()


@router.post("/levels", response_model=LevelOut, status_code=201)
def create_level(body: LevelIn, db: DB = Depends(get_db)):
    lv = Level(**body.model_dump())
    db.add(lv)
    commit_or_409(db)
    return lv


@router.patch("/levels/{level_id}", response_model=LevelOut)
def update_level(level_id: int, body: LevelIn, db: DB = Depends(get_db)):
    lv = get_or_404(db, Level, level_id)
    lv.name, lv.headcount = body.name, body.headcount
    commit_or_409(db)
    return lv


@router.delete("/levels/{level_id}")
def delete_level(level_id: int, db: DB = Depends(get_db)):
    db.delete(get_or_404(db, Level, level_id))
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ modules
@router.get("/modules", response_model=list[ModuleOut])
def list_modules(level_id: int | None = None, db: DB = Depends(get_db)):
    q = select(Module).order_by(Module.level_id, Module.name)
    if level_id is not None:
        q = q.where(Module.level_id == level_id)
    return db.scalars(q).all()


@router.post("/modules", response_model=ModuleOut, status_code=201)
def create_module(body: ModuleIn, db: DB = Depends(get_db)):
    get_or_404(db, Level, body.level_id)
    m = Module(**body.model_dump())
    db.add(m)
    commit_or_409(db)
    return m


@router.patch("/modules/{module_id}", response_model=ModuleOut)
def update_module(module_id: int, body: ModuleIn, db: DB = Depends(get_db)):
    m = get_or_404(db, Module, module_id)
    for k, v in body.model_dump().items():
        setattr(m, k, v)
    commit_or_409(db)
    return m


@router.delete("/modules/{module_id}")
def delete_module(module_id: int, db: DB = Depends(get_db)):
    db.delete(get_or_404(db, Module, module_id))
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ professors
@router.get("/professors", response_model=list[ProfessorOut])
def list_professors(db: DB = Depends(get_db)):
    return [professor_view(db, p) for p in db.scalars(select(Professor).order_by(Professor.name))]


@router.post("/professors", response_model=ProfessorCreated, status_code=201)
def add_professor(body: ProfessorIn, db: DB = Depends(get_db)):
    if db.scalar(select(Professor).where(Professor.name == body.name.strip())):
        raise HTTPException(409, "A professor with this name already exists")
    p, _, password = create_professor(db, body.name, body.max_sessions)
    for t in body.teaches:
        get_or_404(db, Module, t.module_id)
        set_teaching(db, p.id, t.module_id, t.kinds, t.rank)
    db.commit()
    return {**professor_view(db, p), "password": password}


@router.patch("/professors/{prof_id}", response_model=ProfessorOut)
def update_professor(prof_id: int, body: ProfessorIn, db: DB = Depends(get_db)):
    p = get_or_404(db, Professor, prof_id)
    p.name = body.name.strip()
    if body.max_sessions is not None:
        p.max_sessions = body.max_sessions
    db.execute(delete(Teaching).where(Teaching.professor_id == p.id))
    for t in body.teaches:
        get_or_404(db, Module, t.module_id)
        set_teaching(db, p.id, t.module_id, t.kinds, t.rank)
    commit_or_409(db)
    return professor_view(db, p)


@router.delete("/professors/{prof_id}")
def delete_professor(prof_id: int, db: DB = Depends(get_db)):
    db.delete(get_or_404(db, Professor, prof_id))
    db.commit()
    return {"ok": True}


@router.post("/professors/{prof_id}/reset-password")
def reset_password(prof_id: int, db: DB = Depends(get_db)):
    user = db.scalar(select(User).where(User.professor_id == prof_id))
    if not user:
        raise HTTPException(404, "No account for this professor")
    password = new_password()
    user.password_hash = hash_password(password)
    db.commit()
    return {"username": user.username, "password": password}


@router.get("/professors/{prof_id}/availability", response_model=AvailabilityIn)
def get_prof_availability(prof_id: int, db: DB = Depends(get_db)):
    get_or_404(db, Professor, prof_id)
    return availability_view(db, prof_id)


@router.put("/professors/{prof_id}/availability", response_model=AvailabilityIn)
def set_prof_availability(prof_id: int, body: AvailabilityIn, db: DB = Depends(get_db)):
    """Fill a professor's availability grid on their behalf."""
    get_or_404(db, Professor, prof_id)
    return save_availability(db, prof_id, body)

