from typing import Optional, List
from datetime import datetime
from uuid import uuid4
from beanie import Document, Indexed
from pydantic import Field, BaseModel
from app.models.banner import Banner

class Scent(Document):
    """
    Scent document model for MongoDB using Beanie ODM
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Indexed()  # Correctly indexed field
    description: Optional[str] = None
    image_url: Optional[str] = None
    banner_id: Optional[str] = None
    banner: Optional[Banner] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    
    # Define the collection name in MongoDB
    class Settings:
        name = "scents"
        indexes = [
            "name",
            "is_active",
            "created_at",
            "updated_at"
        ]
        
    # Define example data
    class Config:
        schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Floral",
                "description": "Sweet and floral fragrance",
                "image_url": "https://example.com/images/floral.jpg",
                "banner_id": "123e4567-e89b-12d3-a456-426614174001",
                "is_active": True,
                "created_at": "2023-01-01T00:00:00.000Z",
                "updated_at": "2023-01-02T00:00:00.000Z"
            }
        }
    
    # Helper methods for CRUD operations
    @classmethod
    async def get_active_scents(cls) -> List["Scent"]:
        """Get all active scents"""
        return await cls.find({"is_active": True}).sort("name").to_list()
    
    # Update timestamps on save
    async def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return await super().save(*args, **kwargs)
    
    # Method to get banner for this scent
    async def get_banner(self):
        """Get the banner for this scent"""
        if not self.banner_id:
            return None
        return await Banner.find_one({"id": self.banner_id})

# Pydantic models for API
class ScentBase(BaseModel):
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    banner_id: Optional[str] = None

class ScentCreate(ScentBase):
    pass

class ScentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    banner_id: Optional[str] = None
    is_active: Optional[bool] = None

class ScentResponse(ScentBase):
    id: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True 