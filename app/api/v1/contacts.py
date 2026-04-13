import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.contacts import CheckContactRequest, CheckContactResponse
from app.services.contact_service import ContactService

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/contacts", tags=["Contacts"])


@router.post("/check", response_model=CheckContactResponse, status_code=status.HTTP_200_OK)
async def check_contacts(
    check_contact_request: CheckContactRequest,
    db: Session = Depends(get_db),
):
    """
    Accepts a list of E.164 phone numbers and returns only those that
    belong to active, registered users.

    - 200: Subset of registered numbers returned.
    - 422: Request body failed validation (bad format, empty list, over batch limit).
    - 500: Unexpected server or database error.
    """
    try:
        registered = await ContactService.check_contacts(
            check_contact_request.phone_numbers, db
        )
        return CheckContactResponse(phone_numbers=registered)

    except HTTPException:
        raise

    except Exception as e:
        LOGGER.error(f"Unhandled error in check_contacts endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again.",
        )