"""Request / response shapes. FastAPI turns these into the interactive docs at /docs."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

RoomType = Literal["amphi", "td", "lab"]
Kind = Literal["lecture", "td", "tp"]


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    token: str
    role: str
    username: str
    professor_id: int | None = None


class RoomIn(BaseModel):
    name: str
    type: RoomType
    capacity: int = Field(gt=0)
    active: bool = True


class RoomPatch(BaseModel):
    name: str | None = None
    type: RoomType | None = None
    capacity: int | None = Field(default=None, gt=0)
    active: bool | None = None


class RoomOut(RoomIn):
    id: int


class LevelIn(BaseModel):
    name: str
    headcount: int = Field(gt=0)


class LevelOut(LevelIn):
    id: int


class ModuleIn(BaseModel):
    level_id: int
    name: str
    lecture_per_week: int = Field(default=1, ge=0)
    td_per_week: int = Field(default=0, ge=0)
    tp_per_week: int = Field(default=0, ge=0)


class ModuleOut(ModuleIn):
    id: int


class TeachingIn(BaseModel):
    module_id: int
    kinds: list[Kind] = ["lecture", "td", "tp"]
    rank: int = Field(default=1, ge=1)  # 1 = first choice in the professor's wish list


class ProfessorIn(BaseModel):
    name: str
    max_sessions: int | None = Field(default=None, gt=0)  # empty = the department's default
    teaches: list[TeachingIn] = []


class ProfessorOut(BaseModel):
    id: int
    name: str
    max_sessions: int
    username: str | None = None
    teaches: list[TeachingIn] = []
    availability_filled: bool = False


class ProfessorCreated(ProfessorOut):
    password: str  # shown once, to give to the professor


class SlotRef(BaseModel):
    day: int = Field(ge=0)
    slot: int = Field(ge=0)


class AvailabilityIn(BaseModel):
    unavailable: list[SlotRef]  # "I can't": never scheduled there
    avoid: list[SlotRef] = []  # "I'd rather not": avoided when possible


class ImportCommitIn(BaseModel):
    kind: Literal["rooms", "levels", "modules", "professors"]
    rows: list[dict]


class SessionPatch(BaseModel):
    day: int | None = Field(default=None, ge=0)
    slot: int | None = Field(default=None, ge=0)
    room_id: int | None = None
    professor_id: int | None = None


class AbsenceIn(BaseModel):
    session_id: int
    date: date


class SlotSearchIn(BaseModel):
    group_id: int
    date_from: date | None = None
    date_to: date | None = None
    kind: Kind | None = None
    limit: int = Field(default=10, ge=1, le=50)


class ClaimIn(BaseModel):
    group_id: int
    room_id: int
    date: date
    slot: int = Field(ge=0)
    module_id: int | None = None
    kind: Kind | None = None
