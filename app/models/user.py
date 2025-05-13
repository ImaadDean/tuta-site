from beanie import Document, Link
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
import uuid
from enum import Enum
from datetime import datetime, timezone

class UserRole(str, Enum):
    ADMIN = "admin"
    CLIENT = "client"

class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DELETED = "deleted"

class User(Document):
    """MongoDB User document model using Beanie ODM"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    username: str
    phone_number: Optional[str] = None
    hashed_password: str
    is_active: bool = True
    status: UserStatus = UserStatus.ACTIVE
    role: UserRole = UserRole.CLIENT
    profile_picture: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # These relationships will be handled differently in MongoDB
    # We'll use references instead of SQLAlchemy relationships

    class Settings:
        name = "users"
        indexes = [
            "email",
            "username",
            # You can add compound indexes if needed
            # [("email", 1), ("username", 1)]
        ]

    @classmethod
    async def create_admin_user(cls, email: str, username: str, hashed_password: str):
        """Create an admin user if it doesn't exist"""
        # First check if we have an admin with this username/email
        existing_admin = await cls.find_one({"$or": [
            {"username": username},
            {"email": email}
        ]})

        if existing_admin:
            # If the user exists but isn't admin, make them admin
            if existing_admin.role != UserRole.ADMIN:
                print(f"Converting user {existing_admin.username} to admin role")
                existing_admin.role = UserRole.ADMIN
                await existing_admin.save()
            return existing_admin

        # Create new admin user
        print(f"Creating new admin user: {username}")
        admin_user = cls(
            id=str(uuid.uuid4()),
            email=email,
            username=username,
            hashed_password=hashed_password,
            role=UserRole.ADMIN,
            is_active=True
        )

        await admin_user.insert()
        return admin_user

# Pydantic models for API (these remain mostly the same)
class UserBase(BaseModel):
    email: EmailStr
    username: str
    phone_number: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserInDB(UserBase):
    id: str
    is_active: bool
    status: UserStatus
    role: UserRole
    profile_picture: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class UserOut(UserInDB):
    pass

# Model for updating user information
class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    phone_number: Optional[str] = None
    profile_picture: Optional[str] = None
    status: Optional[UserStatus] = None
    is_active: Optional[bool] = None

