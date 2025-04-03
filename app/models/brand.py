from typing import Optional, List
from datetime import datetime
from uuid import uuid4, UUID
from beanie import Document, Link, Indexed
from pydantic import Field, BaseModel
from app.models.banner import Banner

class Brand(Document):
    """
    Brand document model for MongoDB using Beanie ODM
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Indexed()  # Correctly indexed field
    icon_url: str
    description: Optional[str] = None
    banner_id: Optional[str] = None
    banner: Optional[Banner] = None  # Add this field for the banner relationship
    collection_ids: List[str] = []  # Store references to collections
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    is_active: bool = True
    is_featured: bool = False
    order: int = 0  # For sorting brands on the frontend
    product_count: int = 0
    
    # Define the collection name in MongoDB
    class Settings:
        name = "brands"
        indexes = [
            "name",
            "is_active",
            "is_featured",
            "order",
            "created_at",
            "updated_at"
        ]
        
    # Define example data
    class Config:
        schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174002",
                "name": "Apple",
                "description": "American multinational technology company",
                "icon_url": "https://example.com/logos/apple.png",
                "banner_id": "123e4567-e89b-12d3-a456-426614174003",
                "collection_ids": ["123e4567-e89b-12d3-a456-426614174001"],
                "is_active": True,
                "is_featured": True,
                "order": 1,
                "product_count": 10,
                "created_at": "2023-01-01T00:00:00.000Z",
                "updated_at": "2023-01-02T00:00:00.000Z"
            }
        }
    
    # Helper methods for CRUD operations
    @classmethod
    async def get_active_brands(cls) -> List["Brand"]:
        """Get all active brands"""
        return await cls.find({"is_active": True}).sort("name").to_list()
    
    @classmethod
    async def get_featured_brands(cls) -> List["Brand"]:
        """Get featured brands for homepage display"""
        return await cls.find({"is_active": True, "is_featured": True}).sort("order").to_list()
    
    # Update timestamps on save
    async def save(self, *args, **kwargs):
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
    
    # Method to get collections associated with this brand
    async def get_collections(self) -> List:
        """Get all collections associated with this brand"""
        from app.models.collection import Collection
        if not self.collection_ids:
            return []
        return await Collection.find({"id": {"$in": self.collection_ids}}).to_list()
    
    # Method to add a collection to this brand
    async def add_collection(self, collection_id: str):
        """Add a collection to this brand"""
        if collection_id not in self.collection_ids:
            self.collection_ids.append(collection_id)
            await self.save()
    
    # Method to remove a collection from this brand
    async def remove_collection(self, collection_id: str):
        """Remove a collection from this brand"""
        if collection_id in self.collection_ids:
            self.collection_ids.remove(collection_id)
            await self.save()

# Pydantic models for API
class BrandBase(BaseModel):
    name: str
    icon_url: str
    banner_id: Optional[str] = None
    description: Optional[str] = None

class BrandCreate(BrandBase):
    collection_ids: Optional[List[str]] = []

class BrandUpdate(BaseModel):
    name: Optional[str] = None
    icon_url: Optional[str] = None
    banner_id: Optional[str] = None
    description: Optional[str] = None
    collection_ids: Optional[List[str]] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None
    order: Optional[int] = None

class BrandResponse(BrandBase):
    id: str
    collection_ids: List[str]
    created_at: datetime
    updated_at: Optional[datetime]
    is_active: bool
    is_featured: bool
    order: int
    product_count: int

    class Config:
        orm_mode = True 