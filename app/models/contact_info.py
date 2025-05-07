from datetime import datetime, timezone
from typing import Optional, List, Dict
from pydantic import BaseModel, Field, EmailStr
from beanie import Document
from uuid import uuid4
import logging

class ContactUser(BaseModel):
    """Embedded model for storing user contact information"""
    name: str
    email: str
    phone: Optional[str] = None

class ContactMessage(Document):
    """Model for storing contact form messages"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_info: Optional[ContactUser] = None
    subject: str
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_read: bool = False
    is_replied: bool = False
    replied_at: Optional[datetime] = None
    reply_message: Optional[str] = None
    user_id: Optional[str] = None

    class Settings:
        name = "contact_messages"

    @classmethod
    async def get_by_id(cls, message_id: str):
        """Get a message by its ID"""
        logger = logging.getLogger(__name__)
        logger.info(f"Looking for message with ID: {message_id}")

        # First try with the id field (UUID format)
        message = await cls.find_one({"_id": message_id})

        # If not found, try with _id field if it looks like an ObjectId
        if not message and len(message_id) == 24 and all(c in '0123456789abcdefABCDEF' for c in message_id):
            try:
                from bson import ObjectId
                object_id = ObjectId(message_id)
                message = await cls.find_one({"_id": object_id})
                logger.info(f"Found message using ObjectId: {message_id}")
            except Exception as e:
                logger.error(f"Error using ObjectId: {str(e)}")

        if message:
            logger.info(f"Found message with subject: {message.subject}")
            return message
        else:
            logger.warning(f"Message not found with ID: {message_id}")
            return None

    async def mark_as_read(self):
        """Mark the message as read"""
        self.is_read = True
        await self.save()

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

class ContactMessageCreate(BaseModel):
    """Schema for creating a contact message"""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    subject: str
    message: str
    user_id: Optional[str] = None

class ContactMessageResponse(BaseModel):
    """Schema for contact message response"""
    success: bool
    message: str
