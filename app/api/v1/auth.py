from fastapi import APIRouter, Depends, Request
from fastapi import status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.auth import TokenResponse, VerifyOTPRequest, TokenRefreshRequest, GenerateOTPRequest
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/phone/generate-otp", status_code=status.HTTP_200_OK)
async def generate_otp(
    generate_otp_request: GenerateOTPRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    await AuthService.generate_otp(
        db=db,
        phone_number=generate_otp_request.phone_number,
        country_iso=generate_otp_request.country_iso,
        device_info=generate_otp_request.device_info,
        request=request,
    )
    return {"detail": "OTP sent successfully"}


@router.post("/phone/verify-otp", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def verify_otp(
    verify_otp_request: VerifyOTPRequest,
    db: Session = Depends(get_db),
):
    return await AuthService.verify_otp(
        db=db,
        phone_number=verify_otp_request.phone_number,
        otp=verify_otp_request.otp,
        device_info=verify_otp_request.device_info,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: TokenRefreshRequest,
    db: Session = Depends(get_db),
):
    return await AuthService.refresh_access_token(db=db, refresh_token=request.refresh_token)