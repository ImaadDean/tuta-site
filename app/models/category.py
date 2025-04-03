from typing import Optional, List
from datetime import datetime
from uuid import UUID, uuid4
from beanie import Document, Link, Indexed
from pydantic import Field

class Category(Document):
    """
    Category document model for MongoDB using Beanie ODM
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Indexed()
    description: Optional[str] = None
    icon_url: Optional[str] = None
    banner_id: Optional[str] = None  # Reference to banner for category page
    product_count: int = 0
    is_active: bool = True
    collection_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    
    # Define the collection name in MongoDB
    class Settings:
        name = "categories"
        indexes = [
            "name",
            "is_active",
            "collection_id",
            "banner_id"  # Add index for banner_id
        ]
        
    # Define indexes if needed
    class Config:
        schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Electronics",
                "description": "Electronic devices and accessories",
                "icon_url": "https://res.cloudinary.com/cloud_name/image/upload/v1234567890/categories/electronics.png",
                "banner_id": "123e4567-e89b-12d3-a456-426614174002",  # Example banner ID
                "product_count": 42,
                "is_active": True,
                "collection_id": "123e4567-e89b-12d3-a456-426614174001",
                "created_at": "2023-01-01T00:00:00.000Z",
                "updated_at": "2023-01-02T00:00:00.000Z"
            }
        }
    
    # Helper methods for CRUD operations
    @classmethod
    async def get_active_categories(cls) -> List["Category"]:
        """Get all active categories"""
        return await cls.find({"is_active": True}).to_list()
    
    @classmethod
    async def get_by_collection(cls, collection_id: str) -> List["Category"]:
        """Get categories by collection ID"""
        return await cls.find({"collection_id": collection_id, "is_active": True}).to_list()
    
    # Update timestamps on save
    async def save(self, *args, **kwargs):
        if not self.created_at:
            self.created_at = datetime.now()
        self.updated_at = datetime.now()
        return await super().save(*args, **kwargs)
    
    # Method to increment product count
    async def increment_product_count(self, amount: int = 1):
        """Increment the product count by the specified amount"""
        self.product_count += amount
        await self.save()
    
    # Method to decrement product count
    async def decrement_product_count(self, amount: int = 1):
        """Decrement the product count by the specified amount"""
        self.product_count = max(0, self.product_count - amount)
        await self.save() 