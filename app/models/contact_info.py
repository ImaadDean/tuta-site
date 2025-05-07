from datetime import datetime, timezone
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from beanie import Document
from uuid import uuid4

class SocialMediaPlatform(BaseModel):
    """Model for storing social media platform information"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    url: str
    icon_url: Optional[str] = None
    order: int = 0

    class Config:
        # This ensures proper serialization
        orm_mode = True

class ContactInfo(Document):
    """Model for storing contact information"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    address: str
    city: str
    country: str
    phone_numbers: List[str]
    email_addresses: List[str]
    business_hours: Dict[str, str] = Field(
        default={
            "monday_friday": "8:00 AM - 6:00 PM",
            "saturday": "9:00 AM - 4:00 PM",
            "sunday": "Closed"
        }
    )
    # Keep the old field for backward compatibility
    social_media: Dict[str, str] = Field(
        default={
            "facebook": "",
            "twitter": "",
            "instagram": ""
        }
    )
    # New field for flexible social media platforms
    social_platforms: List[SocialMediaPlatform] = Field(default=[])
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    class Settings:
        name = "contact_info"

    @classmethod
    async def get_active(cls):
        """Get the currently active contact information"""
        contact_info = await cls.find_one({"is_active": True})

        # Ensure social_platforms is initialized and properly converted
        if contact_info:
            # If social_platforms is not set or is None, initialize it as an empty list
            if not hasattr(contact_info, 'social_platforms') or contact_info.social_platforms is None:
                contact_info.social_platforms = []

            # If social_platforms is a dict or list of dicts, convert to SocialMediaPlatform objects
            elif isinstance(contact_info.social_platforms, list):
                platforms = []
                for platform in contact_info.social_platforms:
                    if isinstance(platform, dict):
                        platforms.append(SocialMediaPlatform(**platform))
                    else:
                        platforms.append(platform)
                contact_info.social_platforms = platforms

        return contact_info


