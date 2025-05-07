from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailStr
from beanie import Document
from uuid import uuid4

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
    created_at: datetime = Field(default_factory=datetime.utcnow)
    read: bool = False
    replied: bool = False
    replied_at: Optional[datetime] = None
    reply_message: Optional[str] = None
    user_id: Optional[str] = None
    
    class Settings:
        name = "contact_messages"

class ContactMessageCreate(BaseModel):
    """Schema for creating a contact message"""
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    subject: str
    message: str
    user_id: Optional[str] = None

class ContactMessageResponse(BaseModel):
    """Schema for contact message response"""
    success: bool
    message: str
