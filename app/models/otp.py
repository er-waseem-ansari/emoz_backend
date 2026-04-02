from app.database import Base
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func

class OTPVerification(Base):
    __tablename__ = "otp_verifications"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Core OTP Fields
    phone_number = Column(String(15), nullable=False, index=True)  # E.164 format: +919876543210
    country_code = Column(String(5), nullable=False)  # Store country code separately for easier querying
    otp_hash = Column(String(255), nullable=False)  # Hashed OTP (never store plain text in production)

    # Status & Attempts
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_attempts = Column(Integer, default=0, nullable=False)
    invalidated = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    # Security & Tracking
    ip_address = Column(String(45), nullable=True)  # IPv6 support (45 chars)
    user_agent = Column(String(512), nullable=True)
    device_info = Column(String(255), nullable=True)  # Flutter device fingerprint
