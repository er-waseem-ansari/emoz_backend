import re
from pydantic import BaseModel, Field, field_validator
from typing import Optional

_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class GenerateOTPRequest(BaseModel):
    phone_number: str = Field(..., alias="phoneNumber")   # Full E.164: +919876543210
    country_iso: Optional[str] = Field(None, alias="countryIso")  # ISO 3166-1 alpha-2: "IN"
    device_info: Optional[str] = Field(None, alias="deviceInfo")

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not _E164_RE.match(v):
            raise ValueError("phone_number must be in E.164 format (e.g. +919876543210)")
        return v

    model_config = {"populate_by_name": True}


class VerifyOTPRequest(BaseModel):
    phone_number: str = Field(..., alias="phoneNumber")   # Full E.164: +919876543210
    otp: str = Field(..., alias="otp")
    device_info: Optional[str] = Field(None, alias="deviceInfo")

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not _E164_RE.match(v):
            raise ValueError("phone_number must be in E.164 format (e.g. +919876543210)")
        return v

    model_config = {"populate_by_name": True}


class TokenRefreshRequest(BaseModel):
    refresh_token: str = Field(..., alias="refreshToken")

    model_config = {"populate_by_name": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginResponse(BaseModel):
    token_details: TokenResponse
    is_new_user: bool = Field(..., alias="isNewUser")
    user_id: int = Field(..., alias="userId")

    model_config = {"populate_by_name": True}