from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field, EmailStr
from beanie import Document
from uuid import uuid4
import logging

class MessageUser(BaseModel):
    """Embedded model for storing user contact information for messages"""
    name: str
    email: str
    phone: Optional[str] = None

class Message(Document):
    """Model for storing messages sent by users"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_info: Optional[MessageUser] = None
    subject: str
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_read: bool = False
    user_id: Optional[str] = None

    class Settings:
        name = "user_messages"

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

class MessageCreate(BaseModel):
    """Schema for creating a message"""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    subject: str
    message: str
    user_id: Optional[str] = None

class MessageResponse(BaseModel):
    """Schema for message response"""
    success: bool
    message: str
