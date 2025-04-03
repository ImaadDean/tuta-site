from beanie import Document, Link
from typing import Optional
from pydantic import Field
from datetime import datetime
import uuid

class PasswordResetToken(Document):
    """MongoDB password reset token document model using Beanie ODM"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str  # Reference to User id
    token: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    is_used: bool = False
    
    class Settings:
        name = "password_reset_tokens"
        indexes = [
            "user_id",
            "token",
            [("token", 1), ("is_used", 1)]
        ]

# Define a model for creating tokens
class PasswordResetTokenCreate(Document):
    user_id: str
    token: str
    created_at: datetime
    expires_at: datetime
    is_used: bool = False
