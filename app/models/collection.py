from typing import Optional, List
from datetime import datetime
from uuid import uuid4
from beanie import Document, Link, Indexed
from pydantic import Field, BaseModel

class Collection(Document):
    """
    Collection document model for MongoDB using Beanie ODM
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Indexed()  # Correctly indexed field
    description: Optional[str] = None
    image_url: Optional[str] = None
    brand_ids: List[str] = []  # Store references to brands
    is_active: bool = True
    is_featured: bool = False
    order: int = 0  # For sorting collections on the frontend
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    
    # Define the collection name in MongoDB
    class Settings:
        name = "collections"
        indexes = [
            "name",
            "is_active",
            "is_featured"
        ]
        
    # Define example data
    class Config:
        schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174001",
                "name": "Summer Collection",
                "description": "Our latest summer styles",
                "image_url": "https://example.com/images/summer-collection.jpg",
                "brand_ids": ["123e4567-e89b-12d3-a456-426614174002"],
                "is_active": True,
                "is_featured": True,
                "order": 1,
                "created_at": "2023-01-01T00:00:00.000Z",
                "updated_at": "2023-01-02T00:00:00.000Z"
            }
        }
    
    # Helper methods for CRUD operations
    @classmethod
    async def get_active_collections(cls) -> List["Collection"]:
        """Get all active collections"""
        return await cls.find({"is_active": True}).sort("order").to_list()
    
    @classmethod
    async def get_featured_collections(cls) -> List["Collection"]:
        """Get featured collections for homepage display"""
        return await cls.find({"is_active": True, "is_featured": True}).sort("order").to_list()
    
    # Update timestamps on save
    async def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return await super().save(*args, **kwargs)
    
    # Method to get categories in this collection
    async def get_categories(self) -> List:
        """Get all categories in this collection"""
        from app.models.category import Category
        return await Category.find({"collection_id": self.id, "is_active": True}).to_list()
        
    # Method to get brands associated with this collection
    async def get_brands(self) -> List:
        """Get all brands associated with this collection"""
        from app.models.brand import Brand
        if not self.brand_ids:
            return []
        return await Brand.find({"id": {"$in": self.brand_ids}}).to_list()
    
    # Method to add a brand to this collection
    async def add_brand(self, brand_id: str):
        """Add a brand to this collection"""
        if brand_id not in self.brand_ids:
            self.brand_ids.append(brand_id)
            await self.save()
            
            # Update the brand's collection_ids as well
            from app.models.brand import Brand
            brand = await Brand.find_one({"id": brand_id})
            if brand and self.id not in brand.collection_ids:
                await brand.add_collection(self.id)
    
    # Method to remove a brand from this collection
    async def remove_brand(self, brand_id: str):
        """Remove a brand from this collection"""
        if brand_id in self.brand_ids:
            self.brand_ids.remove(brand_id)
            await self.save()
            
            # Update the brand's collection_ids as well
            from app.models.brand import Brand
            brand = await Brand.find_one({"id": brand_id})
            if brand and self.id in brand.collection_ids:
                await brand.remove_collection(self.id)

# Pydantic models for API
class CollectionBase(BaseModel):
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = True
    is_featured: Optional[bool] = False
    order: Optional[int] = 0

class CollectionCreate(CollectionBase):
    brand_ids: Optional[List[str]] = []

class CollectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None
    order: Optional[int] = None
    brand_ids: Optional[List[str]] = None

class CollectionResponse(CollectionBase):
    id: str
    brand_ids: List[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        orm_mode = True 