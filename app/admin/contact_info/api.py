from fastapi import APIRouter, Request, Depends, HTTPException, status, Body
from fastapi.responses import JSONResponse
from typing import Optional, List
from app.models.contact_info import ContactInfo
from app.models.user import User
from app.auth.jwt import get_current_active_admin
from app.admin.contact_info import router
from app.database import get_db
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
from datetime import datetime, timezone
from pydantic import BaseModel
from uuid import uuid4

# Configure logging
logger = logging.getLogger(__name__)

# Import image utility
from app.utils.image import validate_and_save_social_media_icon
from fastapi import File, UploadFile

class SocialMediaPlatformRequest(BaseModel):
    """Request model for social media platform"""
    id: Optional[str] = None
    name: str
    url: str
    icon_url: Optional[str] = None
    order: int = 0

class ContactInfoUpdateRequest(BaseModel):
    """Request model for updating contact information"""
    address: str
    city: str
    country: str
    phone_numbers: List[str]
    email_addresses: List[str]
    business_hours: dict
    social_media: dict  # Keep for backward compatibility
    social_platforms: List[SocialMediaPlatformRequest] = []

@router.post("/api/settings")
async def update_contact_info(
    contact_data: ContactInfoUpdateRequest,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Update contact information
    """
    try:
        # Get current contact info or create new one
        contact_info = await ContactInfo.get_active()

        # Convert social platform requests to model objects
        from app.models.contact_info import SocialMediaPlatform
        social_platforms = []
        for platform in contact_data.social_platforms:
            social_platforms.append(
                SocialMediaPlatform(
                    id=platform.id or str(uuid4()),
                    name=platform.name,
                    url=platform.url,
                    icon_url=platform.icon_url,
                    order=platform.order
                )
            )

        if contact_info:
            # Update existing contact info
            contact_info.address = contact_data.address
            contact_info.city = contact_data.city
            contact_info.country = contact_data.country
            contact_info.phone_numbers = contact_data.phone_numbers
            contact_info.email_addresses = contact_data.email_addresses
            contact_info.business_hours = contact_data.business_hours
            contact_info.social_media = contact_data.social_media
            contact_info.social_platforms = social_platforms
            contact_info.updated_at = datetime.now(timezone.utc)

            await contact_info.save()
        else:
            # Create new contact info
            contact_info = ContactInfo(
                address=contact_data.address,
                city=contact_data.city,
                country=contact_data.country,
                phone_numbers=contact_data.phone_numbers,
                email_addresses=contact_data.email_addresses,
                business_hours=contact_data.business_hours,
                social_media=contact_data.social_media,
                social_platforms=social_platforms,
                is_active=True
            )

            await contact_info.save()

        return JSONResponse(
            content={"success": True, "message": "Contact information updated successfully"}
        )
    except Exception as e:
        logger.error(f"Error updating contact information: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "message": f"Could not update contact information: {str(e)}"}
        )

@router.post("/api/upload-social-icon")
async def upload_social_media_icon(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_admin)
):
    """
    Upload a social media icon and return the URL
    """
    try:
        # Validate and save the icon
        icon_url = await validate_and_save_social_media_icon(file)

        return JSONResponse(
            content={
                "success": True,
                "message": "Icon uploaded successfully",
                "icon_url": icon_url
            }
        )
    except HTTPException as he:
        # Re-raise HTTP exceptions with the same status code
        return JSONResponse(
            status_code=he.status_code,
            content={"success": False, "message": he.detail}
        )
    except Exception as e:
        logger.error(f"Error uploading social media icon: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "message": f"Could not upload icon: {str(e)}"}
        )
