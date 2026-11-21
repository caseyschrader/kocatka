"""Database tables. Only the data listed in the brief's privacy rules is stored."""

from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """SQLite hands datetimes back without a timezone. They are always UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    # The Telegram user id is the primary key, so there is no second id to map.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    first_name: Mapped[str] = mapped_column(String(64))
    adult_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), primary_key=True, autoincrement=False
    )
    gender: Mapped[str] = mapped_column(String(16))  # "female" | "male"
    preference: Mapped[str] = mapped_column(String(16))  # "women" | "men" | "everyone"
    age: Mapped[int] = mapped_column(Integer)
    # Age range of the people this user wants to see. Never below 18.
    age_min: Mapped[int] = mapped_column(Integer)
    age_max: Mapped[int] = mapped_column(Integer)
    city: Mapped[str] = mapped_column(String(64))
    bio: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship()
    photos: Mapped[list["Photo"]] = relationship(order_by="Photo.position")


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("profiles.user_id"), index=True)
    # Telegram keeps the image. We only store its file id, never the bytes.
    file_id: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer)


class Swipe(Base):
    """One Like or Pass. The unique constraint means one decision per pair."""

    __tablename__ = "swipes"
    __table_args__ = (UniqueConstraint("viewer_id", "target_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    viewer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    target_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(8))  # "like" | "pass"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Match(Base):
    """A mutual like. user_a is always the smaller id, so each pair has one row."""

    __tablename__ = "matches"
    # sqlite_autoincrement: never reuse an id, because events refer to match ids.
    __table_args__ = (UniqueConstraint("user_a", "user_b"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_a: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    user_b: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    # "pending" | "active" | "expired" | "closed" (blocked, reported or banned)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_sender: Mapped[int | None] = mapped_column(BigInteger)


class ChatMessage(Base):
    """One relayed message. The text itself is never stored, only that it happened."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(Integer, ForeignKey("matches.id"), index=True)
    sender_id: Mapped[int] = mapped_column(BigInteger, index=True)
    length: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Block(Base):
    __tablename__ = "blocks"
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    blocker_id: Mapped[int] = mapped_column(BigInteger, index=True)
    blocked_id: Mapped[int] = mapped_column(BigInteger, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporter_id: Mapped[int] = mapped_column(BigInteger, index=True)
    reported_id: Mapped[int] = mapped_column(BigInteger, index=True)
    reason: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Ban(Base):
    """Kept even after /delete_me, so a banned person cannot simply sign up again.

    Holds only the Telegram id. Flagged for legal review.
    """

    __tablename__ = "bans"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    banned_by: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Event(Base):
    """Append-only analytics log. Rows are never edited, except to anonymise on /delete_me.

    user_id is who acted, target_id is the other person (if any). Properties hold
    only non-identifying details such as match_id, reason or message length.
    """

    __tablename__ = "events"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    target_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
