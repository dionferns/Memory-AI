"""SQLAlchemy 2.0 typed declarative models for the v1 schema.

All seven base tables live here in a single module (per ticket 02's locked
decisions): ``users``, ``user_settings``, ``subjects``, ``folders``,
``sources``, ``cards``, ``reviews``. Cascade deletes are enforced at the DB
level via ``ondelete="CASCADE"`` on foreign keys down the
subject -> folder -> source -> card and card -> reviews chains.

Timestamp columns are timezone-aware (``TIMESTAMPTZ``), stored in UTC, with
one exception: ``cards.due_date`` is a bare ``DATE`` since "due today" is a
day-boundary concept, not an instant.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# All ``datetime`` columns are timezone-aware (Postgres ``TIMESTAMPTZ``),
# storing values in UTC. ``cards.due_date`` is the one exception and uses a
# bare ``Date`` column instead.
_TIMESTAMPTZ = DateTime(timezone=True)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMPTZ, nullable=False)


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    daily_review_cap: Mapped[int] = mapped_column(nullable=False)
    timezone: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMPTZ, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(_TIMESTAMPTZ, nullable=False)


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMPTZ, nullable=False)

    # For eager-loading a user's subjects together with their folders in a
    # single query shape (ticket 04 decision #7) -- this relationship exists
    # purely to support that read pattern via `selectinload`; deletes still
    # go through a plain `DELETE` on the row with cascading handled entirely
    # by the DB's `ON DELETE CASCADE` (ticket 04 decision #13), not by any
    # ORM-level cascade configured here. `passive_deletes=True` is required
    # for that split to actually work: without it, the ORM's default
    # behavior on a parent delete is to try to UPDATE any *already-loaded*
    # child rows' FK to NULL, which both duplicates the DB's own cascade
    # logic and fails outright here since `folders.subject_id` is NOT NULL.
    folders: Mapped[list["Folder"]] = relationship(
        back_populates="subject",
        order_by="Folder.created_at, Folder.id",
        passive_deletes=True,
    )


class Folder(Base):
    __tablename__ = "folders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMPTZ, nullable=False)

    subject: Mapped["Subject"] = relationship(back_populates="folders")

    # Same eager-load-friendly / DB-cascade-only split as `Subject.folders`
    # above (ticket 04 decision #7 / #13): this relationship exists so the
    # folder view can `selectinload` a folder's sources in one follow-up
    # query, while actual deletes are handled entirely by the DB's
    # `ON DELETE CASCADE` on `sources.folder_id`, not by the ORM.
    sources: Mapped[list["Source"]] = relationship(
        back_populates="folder",
        order_by="Source.created_at, Source.id",
        passive_deletes=True,
    )


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        # Ticket 05 decision #10: per-folder filename uniqueness is
        # case-insensitive and enforced at the DB level, not just in
        # application code -- a functional unique index on
        # `(folder_id, lower(filename))`. The upload route attempts the
        # insert and catches the resulting `IntegrityError` (same
        # insert-then-catch pattern already locked for duplicate emails in
        # ticket 03), rather than pre-checking with a separate `SELECT`.
        Index(
            "ix_sources_folder_id_lower_filename",
            "folder_id",
            text("lower(filename)"),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    folder_id: Mapped[int] = mapped_column(
        ForeignKey("folders.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(nullable=False)
    file_type: Mapped[str] = mapped_column(nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(nullable=False)
    error_message: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMPTZ, nullable=False)

    folder: Mapped["Folder"] = relationship(back_populates="sources")

    # Read-only convenience relationship for rendering a source's generated
    # cards (ticket 06). `viewonly=True` because writes go through explicit
    # `INSERT`/`DELETE` statements in the generation job and convert route
    # (replace-on-retrigger, ticket 06 decision #5) rather than the ORM's
    # own add/cascade machinery -- this relationship exists purely for the
    # lazy-loaded read side.
    cards: Mapped[list["Card"]] = relationship(
        order_by="Card.created_at, Card.id",
        viewonly=True,
    )


class Card(Base):
    __tablename__ = "cards"
    __table_args__ = (Index("ix_cards_folder_id", "folder_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    folder_id: Mapped[int] = mapped_column(
        ForeignKey("folders.id", ondelete="CASCADE"), nullable=False
    )
    front: Mapped[str] = mapped_column(Text, nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)
    ease_factor: Mapped[float] = mapped_column(nullable=False, default=2.5)
    interval_days: Mapped[int] = mapped_column(nullable=False, default=0)
    repetitions: Mapped[int] = mapped_column(nullable=False, default=0)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(_TIMESTAMPTZ, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMPTZ, nullable=False)


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False)
    grade: Mapped[str] = mapped_column(nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(_TIMESTAMPTZ, nullable=False)
    prev_interval_days: Mapped[int] = mapped_column(nullable=False)
    new_interval_days: Mapped[int] = mapped_column(nullable=False)
