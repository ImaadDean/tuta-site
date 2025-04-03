from typing import Optional, List
from uuid import UUID, uuid4
from datetime import datetime
from beanie import Document, Indexed, Link
from pydantic import BaseModel, Field

class Address(Document):
    """
    Address model for storing user addresses
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: Optional[str] = None
    name: str = Indexed()
    address: str
    city: str
    country: str
    is_default: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "addresses"
        indexes = [
            "name",
            "user_id",
            "is_default"
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "123e4567-e89b-12d3-a456-426614174001",
                "name": "Home",
                "address": "123 Main St",
                "city": "New York",
                "country": "USA",
                "is_default": True,
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00"
            }
        }

    async def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return await super().save(*args, **kwargs)

    @classmethod
    async def get_user_addresses(cls, user_id: str) -> List["Address"]:
        """
        Get all addresses for a user
        """
        return await cls.find({"user_id": user_id}).to_list()

    @classmethod
    async def get_default_address(cls, user_id: str) -> Optional["Address"]:
        """
        Get the default address for a user
        """
        return await cls.find_one({"user_id": user_id, "is_default": True})

    async def set_as_default(self) -> None:
        """
        Set this address as the default address for the user
        """
        # First, unset any existing default address
        await self.find({"user_id": self.user_id}).update({"$set": {"is_default": False}})
        # Then set this address as default
        self.is_default = True
        await self.save()

# Pydantic models for API requests/responses
class AddressBase(BaseModel):
    name: str
    address: str
    city: str
    country: str
    is_default: bool = False

class AddressCreate(AddressBase):
    user_id: Optional[str] = None

class AddressUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    is_default: Optional[bool] = None

class AddressResponse(AddressBase):
    id: str
    user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True 