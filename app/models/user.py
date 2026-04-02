from sqlalchemy import Column, Integer, String, DateTime, Enum, Boolean
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=True)
    phone = Column(String(20), unique=True, index=True, nullable=True)
    country_code = Column(String(5), nullable=True)  # New field for country code (e.g., +91)
    password_hash = Column(String(255), nullable=True)  # Null for OAuth users
    profile_picture_url = Column(String(500), nullable=True)  # New field for profile picture URL
    device_info = Column(String(255), nullable=True)  # New field for device information (e.g., "Flutter App v1.0 on Android 11")

    # OAuth
    google_id = Column(String(255), unique=True, nullable=True, index=True)
    firebase_uid = Column(String(255), unique=True, nullable=True, index=True)

    # New additions
    is_active = Column(Boolean, default=True)  # For account suspension
    is_verified = Column(Boolean, default=False)  # Verification badge
    last_login = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())