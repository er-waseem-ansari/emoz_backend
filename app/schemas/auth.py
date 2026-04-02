from pydantic import BaseModel, Field
from typing import Optional

class GenerateOTPRequest(BaseModel):
    phone_number: str = Field(..., alias='phoneNumber')  # E.164 format: +919876543210
    country_code: str = Field(None, alias='countryCode')  # Optional country code for better formatting
    device_info: Optional[str] = Field(None, alias='deviceInfo')  # Flutter device fingerprint

class VerifyOTPRequest(BaseModel):
    phone_number: str = Field(..., alias='phoneNumber')  # Firebase token
    country_code: str = Field(None, alias='countryCode')  # Optional country code for better formatting
    otp: str = Field(..., alias='otp')  # OTP code
    device_info: Optional[str] = Field(None, alias='deviceInfo')

class TokenRefreshRequest(BaseModel):
    refresh_token: str = Field(..., alias='refreshToken')

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class LoginResponse(BaseModel):
    token_details: TokenResponse
    is_new_user: bool = Field(..., alias='isNewUser')
    user_id: int = Field(..., alias='userId')