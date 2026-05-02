from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    user_name = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_email_verified = Column(Boolean, default=False, nullable=False)
    email_verification_token_hash = Column(String, nullable=True)
    email_verification_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    password_reset_token_hash = Column(String, nullable=True)
    password_reset_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    refresh_token_hash = Column(String, nullable=True)
    refresh_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
