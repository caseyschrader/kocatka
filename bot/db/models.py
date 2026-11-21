"""Database tables. Only the data listed in the brief's privacy rules is stored."""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
