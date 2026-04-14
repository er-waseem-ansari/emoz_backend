import logging
from typing import List

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.contacts import RegisteredContact, normalize_phone

LOGGER = logging.getLogger(__name__)


class ContactService:
    @staticmethod
    async def check_contacts(
        phone_numbers: List[str], db: Session
    ) -> List[RegisteredContact]:
        """
        Accepts a list of phone numbers (already validated, in original client format).

        - Normalizes each number (strip spaces/dashes/parens) for the DB lookup.
        - Queries the users table in a single IN clause — no N+1 queries.
        - Returns RegisteredContact objects with phoneNumber in the same format
          as received from the client and the corresponding userId.
        - Deduplicates by normalized form to avoid redundant DB work.
        """
        try:
            # Build normalized → original mapping (first occurrence wins on duplicates)
            normalized_to_original: dict[str, str] = {}
            for original in phone_numbers:
                normalized = normalize_phone(original)
                if normalized not in normalized_to_original:
                    normalized_to_original[normalized] = original

            if not normalized_to_original:
                return []

            # Single batch query — fetch phone + id for all matching active users
            rows = (
                db.query(User.phone, User.id)
                .filter(
                    User.phone.in_(list(normalized_to_original.keys())),
                    User.is_active.is_(True),
                )
                .all()
            )

            # Map each DB-normalized number back to the original client format
            result = [
                RegisteredContact(
                    phone_number=normalized_to_original.get(row.phone, row.phone),
                    user_id=row.id,
                )
                for row in rows
            ]

            LOGGER.info(
                "check_contacts: queried %d numbers, found %d registered",
                len(normalized_to_original),
                len(result),
            )
            return result

        except SQLAlchemyError as e:
            db.rollback()
            LOGGER.error("Database error in check_contacts: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error. Please try again.",
            )

        except HTTPException:
            raise

        except Exception as e:
            LOGGER.error("Unexpected error in check_contacts: %s", e, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred. Please try again.",
            )