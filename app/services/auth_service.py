from typing import Optional
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status, Request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, and_
from app.config import get_settings
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.otp import OTPVerification
from app.models.token import RefreshToken
from app.models.user import User
import secrets
import bcrypt
import logging

from app.schemas.auth import TokenResponse
from app.services.fast2sms import Fast2SMS

LOGGER = logging.getLogger(__name__)
settings = get_settings()

class AuthService:

    @staticmethod
    async def generate_otp(db: Session, phone_number: str, country_code: str, device_info: str, request: Request) -> None:
        """Generates and sends OTP to the given phone number"""
        try:
            # Step 1: Fetch ALL unverified, non-invalidated OTPs for this phone (SINGLE QUERY)
            existing_otps = db.query(OTPVerification).filter(
                OTPVerification.phone_number == phone_number,
                OTPVerification.country_code == country_code,
                OTPVerification.is_verified == False,
                OTPVerification.invalidated == False
            ).all()  # Get all records at once

            # Step 2: Rate Limiting - Check if >= 3 OTPs in last hour
            one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
            recent_count = sum(
                1 for otp in existing_otps
                if otp.created_at >= one_hour_ago
            )

            if recent_count >= 3:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many OTP requests. Please try again after 1 hour."
                )

            # Step 3: Cooldown Period - Check if any OTP created in last 1 minute
            one_minute_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
            recent_otp = next(
                (otp for otp in existing_otps if otp.created_at >= one_minute_ago),
                None
            )

            if recent_otp:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Please wait 1 minute before requesting a new OTP."
                )

            # Step 4: Invalidate ALL existing OTPs at once
            if existing_otps:
                for otp in existing_otps:
                    otp.invalidated = True
                db.commit()  # Bulk update

            # Step 5: Generate secure OTP
            # otp_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
            otp_code = "123456" #Only for testing purpose

            otp_hash = bcrypt.hashpw(otp_code.encode('utf-8'), bcrypt.gensalt())

            new_otp = OTPVerification(
                phone_number=phone_number,
                country_code=country_code,
                otp_hash=otp_hash.decode('utf-8'),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                device_info=device_info,
                ip_address = request.client.host,
                user_agent = request.headers.get("user-agent")
            )

            db.add(new_otp)
            db.commit()

            # sms_result = Fast2SMS.send_sms(
            #     to=country_code+phone_number,
            #     message=f"Your OTP is {otp_code}. Valid for 5 minutes."
            # )
            #
            #
            # LOGGER.error(sms_result)
            #
            # if not sms_result["success"]:
            #     LOGGER.error(f"Failed to send SMS: {sms_result['error']}")
            #     # OTP is saved in DB but SMS failed
            #     raise HTTPException(
            #         status_code=500,
            #         detail="Failed to send OTP. Please try again."
            #     )

            LOGGER.info(f"OTP sent successfully to {country_code+phone_number}")

        except SQLAlchemyError as e:
            db.rollback()
            LOGGER.error(f"Database error while generating OTP: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Database error. Please try again."
            )

        except HTTPException:
            # Re-raise HTTPException as-is
            raise

        except Exception as e:
            db.rollback()
            LOGGER.error(f"Unexpected error while generating OTP: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Failed to generate OTP. Please try again."
            )


    @staticmethod
    async def verify_otp(db: Session, phone_number: str, country_code: str, otp: str, device_info: str) -> TokenResponse:

        try:
            # Step 1: Find the latest valid OTP record
            record = db.query(OTPVerification).filter(
                OTPVerification.phone_number == phone_number,
                OTPVerification.country_code == country_code,
                OTPVerification.is_verified == False,
                OTPVerification.invalidated == False,
                OTPVerification.expires_at > datetime.now(timezone.utc)
            ).order_by(OTPVerification.created_at.desc()).first()

            # Step 2: Check if valid OTP exists
            if not record:
                LOGGER.warning(f"No valid OTP found for phone: {phone_number}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No valid OTP found or OTP has expired. Please request a new OTP."
                )

            # Step 3: Check if max attempts exceeded
            if record.verification_attempts >= settings.OTP_MAX_ATTEMPTS:
                LOGGER.warning(
                    f"Max verification attempts exceeded for phone: {phone_number}, "
                    f"OTP ID: {record.id}"
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Maximum verification attempts exceeded. Please request a new OTP."
                )

            # Step 4: Verify the OTP hash
            try:
                is_valid = bcrypt.checkpw(
                    otp.encode('utf-8'),
                    record.otp_hash.encode('utf-8')
                )
            except Exception as e:
                LOGGER.error(f"Bcrypt verification error: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error verifying OTP. Please try again."
                )

            if not is_valid:
                # Wrong OTP - increment attempts
                try:
                    record.verification_attempts += 1
                    db.commit()
                except SQLAlchemyError as e:
                    db.rollback()
                    LOGGER.error(f"Failed to increment verification attempts: {str(e)}")
                    # Continue to show error to user even if DB update fails

                remaining_attempts = settings.OTP_MAX_ATTEMPTS - record.verification_attempts

                LOGGER.warning(
                    f"Invalid OTP attempt for phone: {phone_number}, "
                    f"Attempts: {record.verification_attempts}/{settings.OTP_MAX_ATTEMPTS}"
                )

                if remaining_attempts > 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid OTP. Please try again"
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Invalid OTP. Maximum attempts exceeded. Please request a new OTP."
                    )

            # Step 5: OTP is correct - Mark as verified
            try:
                record.is_verified = True
                record.verified_at = datetime.now(timezone.utc)
                db.commit()
                LOGGER.info(f"OTP verified successfully for phone: {phone_number}")
            except SQLAlchemyError as e:
                db.rollback()
                LOGGER.error(f"Failed to mark OTP as verified: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Database error while verifying OTP. Please try again."
                )

            # Step 6: Check if user already exists
            try:
                existing_user = db.query(User).filter(
                    User.phone == phone_number,
                    User.country_code == country_code
                ).first()
            except SQLAlchemyError as e:
                LOGGER.error(f"Database error while fetching user: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Database error. Please try again."
                )

            if existing_user:
                # User exists - use existing account
                user = existing_user


                LOGGER.info(f"Existing user logged in: {phone_number} (User ID: {user.id})")
            else:
                # New user - create account
                try:
                    user = User(
                        phone=phone_number,
                        country_code=country_code,
                        device_info = device_info
                    )
                    db.add(user)
                    db.commit()
                    db.refresh(user)

                    LOGGER.info(f"New user created: {phone_number} (User ID: {user.id})")
                except IntegrityError as e:
                    db.rollback()
                    LOGGER.error(f"Integrity error while creating user: {str(e)}")
                    # Possible race condition - user was created between check and insert
                    # Try to fetch again
                    existing_user = db.query(User).filter(User.phone == phone_number, User.country_code == country_code).first()
                    if existing_user:
                        user = existing_user
                        LOGGER.info(f"User found after race condition: {phone_number}")
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to create user account. Please try again."
                        )
                except SQLAlchemyError as e:
                    db.rollback()
                    LOGGER.error(f"Database error while creating user: {str(e)}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to create user account. Please try again."
                    )

            # Step 7: Generate and return tokens
            try:
                return AuthService._generate_token_response(db, user, device_info)
            except Exception as e:
                LOGGER.error(f"Failed to generate tokens for user {user.id}: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to generate authentication tokens. Please try again."
                )

        except HTTPException:
            # Re-raise HTTPExceptions as-is (already have proper status codes and messages)
            raise

        except Exception as e:
            # Catch any unexpected errors
            db.rollback()
            LOGGER.error(f"Unexpected error in verify_otp: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred. Please try again."
            )

    @staticmethod
    def _generate_token_response(
            db: Session,
            user: User,
            device_info: Optional[str] = None
    ) -> TokenResponse:
        """Helper method to generate access + refresh tokens"""

        # Token payload
        token_data = {
            "sub": str(user.id),
            "phone": user.phone.value,
        }

        # Generate tokens
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        # Store refresh token in DB
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        db_refresh_token = RefreshToken(
            user_id=user.id,
            refresh_token=refresh_token,
            expires_at=expires_at,
            device_info=device_info,
            is_revoked=False
        )

        db.add(db_refresh_token)
        db.commit()

        response = TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )

        return response

    @staticmethod
    async def refresh_access_token(
            db: Session,
            refresh_token: str
    ) -> TokenResponse:
        """Generate new access token using refresh token"""

        try:
            # Decode and verify token
            payload = decode_token(refresh_token)

            # Check token type
            if payload.get('type') != 'refresh':
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type"
                )

            user_id = payload.get('sub')

            # Check if token exists in DB and not revoked
            stmt = select(RefreshToken).where(
                and_(
                    RefreshToken.refresh_token == refresh_token,
                    RefreshToken.user_id == user_id,
                    RefreshToken.is_revoked == False
                )
            )
            result = db.execute(stmt)
            db_token = result.scalar_one_or_none()

            if not db_token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or revoked refresh token"
                )

            # Check expiration
            if db_token.expires_at < datetime.now(timezone.utc):
                db_token.is_revoked = True
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token expired"
                )

            # Get user
            stmt = select(User).where(and_(User.id == user_id))
            result = db.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )

            # Generate new access token
            access_token = create_access_token({
                "sub": str(user.id),
                "phone": user.phone.value,
            })

            response = TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer",
                expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            )

            return response

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid refresh token: {str(e)}"
            )