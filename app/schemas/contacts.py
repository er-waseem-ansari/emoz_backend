from pydantic import BaseModel, Field, field_validator
from typing import List
import re

_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_FORMATTING_CHARS = re.compile(r"[\s\-\(\)\.]")
MAX_BATCH_SIZE = 500


def _normalize(number: str) -> str:
    """Strip common formatting characters (spaces, dashes, parentheses, dots)."""
    return _FORMATTING_CHARS.sub("", number.strip())


class CheckContactRequest(BaseModel):
    phone_numbers: List[str] = Field(..., min_length=1, alias="phoneNumbers")

    @field_validator("phone_numbers")
    @classmethod
    def validate_phone_numbers(cls, numbers: List[str]) -> List[str]:
        if len(numbers) > MAX_BATCH_SIZE:
            raise ValueError(f"Exceeds maximum of {MAX_BATCH_SIZE} numbers per request")

        normalized = []
        for raw in numbers:
            clean = _normalize(raw)
            if not _E164_RE.match(clean):
                raise ValueError(
                    f"'{raw}' cannot be normalised to E.164 format. "
                    "Numbers must include a country prefix (e.g. +919876543210)."
                )
            normalized.append(clean)

        return normalized

    model_config = {"populate_by_name": True}


class CheckContactResponse(BaseModel):
    phone_numbers: List[str] = Field(..., alias="registeredNumbers")

    model_config = {"populate_by_name": True}