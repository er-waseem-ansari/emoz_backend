import logging
from typing import List

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.user import User

LOGGER = logging.getLogger(__name__)


class ContactService:
    @staticmethod
    async def check_contacts(phone_numbers: List[str], db: Session) -> List[str]:
        """
        Returns the subset of the given E.164 phone numbers that belong to
        active, registered users.

        Validation (format, batch size) is enforced at the schema layer before
        this method is reached. The query uses a parameterised IN clause via
        SQLAlchemy — no raw SQL, no injection risk.
        Only users with is_active=True are matched.
        """
        try:
            # Deduplicate to avoid redundant DB work while preserving first-seen order
            unique_numbers: List[str] = list(dict.fromkeys(phone_numbers))

            rows = (
                db.query(User.phone)
                .filter(
                    User.phone.in_(unique_numbers),
                    User.is_active.is_(True),
                )
                .all()
            )

            registered = [row.phone for row in rows]
            LOGGER.info(
                f"check_contacts: queried {len(unique_numbers)} numbers, "
                f"found {len(registered)} registered"
            )
            return registered

        except SQLAlchemyError as e:
            db.rollback()
            LOGGER.error(f"Database error in check_contacts: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error. Please try again.",
            )

        except HTTPException:
            raise

        except Exception as e:
            LOGGER.error(f"Unexpected error in check_contacts: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred. Please try again.",
            )