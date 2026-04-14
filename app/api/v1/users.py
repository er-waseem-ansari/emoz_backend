import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.routing import AliasRoute
from app.core.security import get_current_user_id
from app.database import get_db
from app.models.user import User

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"], route_class=AliasRoute)


class UserProfileOut(BaseModel):
    id: int
    username: Optional[str] = None
    phone: Optional[str] = Field(default=None, alias="phoneNumber")
    profile_picture_url: Optional[str] = Field(default=None, alias="profilePictureUrl")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


@router.get("/{user_id}", response_model=UserProfileOut, status_code=status.HTTP_200_OK)
async def get_user_profile(
    user_id: int,
    db: Session = Depends(get_db),
    _: int = Depends(get_current_user_id),
):
    """
    Returns basic profile info for any active user.

    Flutter should call this to populate its local user-profile cache.
    Fetch once per unknown userId and cache the result — profiles rarely change.

    - 200: Profile returned.
    - 404: User does not exist or is inactive.
    - 401: Missing or invalid token.
    """
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user