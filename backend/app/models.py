"""Database tables."""

from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    """Current UTC time, naive (SQLite stores datetimes without timezone)."""
    return datetime.now(UTC).replace(tzinfo=None)


class AppSetting(Base):
    """Key/value settings edited by the admin (the department's rules, see rules.py)."""

    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(10))  # "admin" | "prof"
    professor_id: Mapped[int | None] = mapped_column(
        ForeignKey("professors.id", ondelete="CASCADE"), nullable=True
    )


class AuthToken(Base):
    """A login. Only a hash of the token is stored."""

    __tablename__ = "auth_tokens"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Level(Base):
    """A level + specialty, e.g. 'L3 SI', with its number of students."""

    __tablename__ = "levels"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    headcount: Mapped[int] = mapped_column(Integer)
    # Headcount and group sizes used the last time groups were built: if they change, the groups of this level are rebuilt automatically at the next generation.
    groups_signature: Mapped[str] = mapped_column(String(80), default="")


class Group(Base):
    """A section (lectures), a TD group, or a TP subgroup. TP ⊂ TD ⊂ section."""

    __tablename__ = "groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    level_id: Mapped[int] = mapped_column(ForeignKey("levels.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(10))  # section | td | tp
    size: Mapped[int] = mapped_column(Integer)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=True
    )


class Module(Base):
    """A course. Weekly load is counted in 1h30 sessions."""

    __tablename__ = "modules"
    __table_args__ = (UniqueConstraint("level_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    level_id: Mapped[int] = mapped_column(ForeignKey("levels.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    lecture_per_week: Mapped[int] = mapped_column(Integer, default=1)
    td_per_week: Mapped[int] = mapped_column(Integer, default=0)
    tp_per_week: Mapped[int] = mapped_column(Integer, default=0)


class Professor(Base):
    __tablename__ = "professors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    max_sessions: Mapped[int] = mapped_column(Integer, default=12)  # per week


class Teaching(Base):
    """Which professor can teach which module, and which kinds (lecture/td/tp)."""

    __tablename__ = "teachings"
    __table_args__ = (UniqueConstraint("professor_id", "module_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    professor_id: Mapped[int] = mapped_column(
        ForeignKey("professors.id", ondelete="CASCADE")
    )
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id", ondelete="CASCADE"))
    kinds: Mapped[str] = mapped_column(String(30), default="lecture,td,tp")
    # Order of preference from the professor's wish list (fiche de voeux): 1 = first choice.
    rank: Mapped[int] = mapped_column(Integer, default=1)


class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    type: Mapped[str] = mapped_column(String(10))  # amphi | td | lab
    capacity: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(
        Boolean, default=True
    )  # False = closed (repairs...)


class Unavailability(Base):
    """A slot a professor tapped on the weekly grid: 'I can't' (hard rule) or, with soft=True,
    'I'd rather not' (the solver avoids it when it can)."""

    __tablename__ = "unavailabilities"
    __table_args__ = (UniqueConstraint("professor_id", "day", "slot"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    professor_id: Mapped[int] = mapped_column(
        ForeignKey("professors.id", ondelete="CASCADE")
    )
    day: Mapped[int] = mapped_column(Integer)
    slot: Mapped[int] = mapped_column(Integer)
    soft: Mapped[bool] = mapped_column(Boolean, default=False)


class Session(Base):
    """One weekly recurring session of the generated timetable."""

    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    professor_id: Mapped[int] = mapped_column(
        ForeignKey("professors.id", ondelete="CASCADE")
    )
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))
    day: Mapped[int] = mapped_column(Integer)
    slot: Mapped[int] = mapped_column(Integer)

    module = relationship("Module", lazy="joined")
    group = relationship("Group", lazy="joined")
    professor = relationship("Professor", lazy="joined")
    room = relationship("Room", lazy="joined")


class Absence(Base):
    """A professor won't come to one occurrence (a date) of a weekly session."""

    __tablename__ = "absences"
    __table_args__ = (UniqueConstraint("session_id", "date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE")
    )
    date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    session = relationship("Session", lazy="joined")


class Claim(Base):
    """An extra / make-up session booked on a precise date.

    The unique constraint on (room, date, slot) is what makes 'first claim wins'
    safe even if two professors tap at the same second.
    """

    __tablename__ = "claims"
    __table_args__ = (UniqueConstraint("room_id", "date", "slot"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    professor_id: Mapped[int] = mapped_column(
        ForeignKey("professors.id", ondelete="CASCADE")
    )
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    module_id: Mapped[int | None] = mapped_column(
        ForeignKey("modules.id", ondelete="SET NULL"), nullable=True
    )
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    slot: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    professor = relationship("Professor", lazy="joined")
    group = relationship("Group", lazy="joined")
    module = relationship("Module", lazy="joined")
    room = relationship("Room", lazy="joined")


class ActionLog(Base):
    __tablename__ = "action_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    username: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(String(400), default="")
