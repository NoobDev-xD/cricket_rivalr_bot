
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Boolean
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True
    )

    username: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    first_name: Mapped[str] = mapped_column(
        String(128), default="Player"
    )


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    chat_id: Mapped[int] = mapped_column(
        BigInteger, index=True
    )

    created_by: Mapped[int] = mapped_column(
        BigInteger
    )

    # New Host permission field
    # Nullable temporarily for existing database compatibility
    host_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )

    overs: Mapped[int] = mapped_column(Integer)

    wickets_limit: Mapped[int] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(
        String(24), default="setup"
    )

    batting_side: Mapped[str] = mapped_column(
        String(1), default="A"
    )

    runs: Mapped[int] = mapped_column(
        Integer, default=0
    )

    batter_runs: Mapped[int] = mapped_column(
        Integer, default=0
    )

    partnership_runs: Mapped[int] = mapped_column(
        Integer, default=0
    )

    wickets: Mapped[int] = mapped_column(
        Integer, default=0
    )

    legal_balls: Mapped[int] = mapped_column(
        Integer, default=0
    )

    striker_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )

    non_striker_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )

    bowler_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )

    group_message_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE")
    )

    name: Mapped[str] = mapped_column(
        String(64)
    )

    captain_id: Mapped[int] = mapped_column(
        BigInteger
    )

    side: Mapped[str] = mapped_column(
        String(1)
    )


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE")
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger
    )

    display_name: Mapped[str] = mapped_column(
        String(128)
    )

    is_captain: Mapped[bool] = mapped_column(
        Boolean, default=False
    )


class BallEvent(Base):
    __tablename__ = "ball_events"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE")
    )

    over_number: Mapped[int] = mapped_column(
        Integer
    )

    ball_number: Mapped[int] = mapped_column(
        Integer
    )

    batter_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )

    bowler_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )

    runs: Mapped[int] = mapped_column(
        Integer, default=0
    )

    extra_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )

    wicket: Mapped[bool] = mapped_column(
        Boolean, default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    
