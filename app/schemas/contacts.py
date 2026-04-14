import re
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator

_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_FORMATTING_CHARS = re.compile(r"[\s\-\(\)\.]")
MAX_BATCH_SIZE = 500


def normalize_phone(number: str) -> str:
    """Strip common formatting characters (spaces, dashes, parentheses, dots)."""
    return _FORMATTING_CHARS.sub("", number.strip())


class CheckContactRequest(BaseModel):
    phone_numbers: List[str] = Field(..., min_length=1, alias="phoneNumbers")

    @field_validator("phone_numbers")
    @classmethod
    def validate_phone_numbers(cls, numbers: List[str]) -> List[str]:
        if len(numbers) > MAX_BATCH_SIZE:
            raise ValueError(f"Exceeds maximum of {MAX_BATCH_SIZE} numbers per request.")

        for raw in numbers:
            clean = normalize_phone(raw)
            if not _E164_RE.match(clean):
                raise ValueError(
                    f"'{raw}' cannot be normalised to E.164 format. "
                    "Numbers must include a country prefix (e.g. +919876543210)."
                )

        # Return originals — normalization happens in the service so the
        # original format can be echoed back in the response.
        return numbers

    model_config = ConfigDict(populate_by_name=True)


class RegisteredContact(BaseModel):
    phone_number: str = Field(alias="phoneNumber")
    user_id: int      = Field(alias="userId")

    model_config = ConfigDict(populate_by_name=True)


class CheckContactResponse(BaseModel):
    registered_numbers: List[RegisteredContact] = Field(
        default_factory=list, alias="registeredNumbers"
    )

    model_config = ConfigDict(populate_by_name=True)