from typing import Optional, List
from uuid import uuid4
from datetime import datetime
from enum import Enum
from beanie import Document, Indexed
from pydantic import BaseModel, Field, validator

class BannerPosition(str, Enum):
    """Enum for banner positions to ensure consistency"""
    HOME_TOP = "home_top"
    CATEGORY_PAGE = "category_page"
    BRAND_PAGE = "brand_page"
    COLLECTION_PAGE = "collection_page"
    SCENT_PAGE = "scent_page"

class Banner(Document):
    """
    Banner model for storing promotional banners
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Indexed()
    subtitle: Optional[str] = None
    description: Optional[str] = None
    image_url: str
    link: Optional[str] = None
    is_active: bool = True
    position: BannerPosition = BannerPosition.HOME_TOP
    priority: int = 0  # Higher number means higher priority
    start_date: Optional[datetime] = None  # When the banner should start displaying
    end_date: Optional[datetime] = None  # When the banner should stop displaying
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "banners"
        indexes = [
            "title",
            "is_active",
            "position",
            "priority"
        ]

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "title": "Summer Sale",
                "subtitle": "Up to 50% off",
                "description": "Shop our biggest sale of the year",
                "image_url": "https://example.com/banner.jpg",
                "link": "/sale",
                "is_active": True,
                "position": "home_top",
                "priority": 10,
                "start_date": "2024-06-01T00:00:00",
                "end_date": "2024-08-31T23:59:59",
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00"
            }
        }

    async def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return await super().save(*args, **kwargs)
    
    @validator('end_date')
    def validate_end_date(cls, end_date, values):
        """Validate that end_date is after start_date if both are provided"""
        start_date = values.get('start_date')
        if start_date and end_date and end_date < start_date:
            raise ValueError('end_date must be after start_date')
        return end_date

    @classmethod
    async def get_active_banners(cls, position: Optional[str] = None, 
                                skip: int = 0, limit: int = 100) -> list["Banner"]:
        """
        Get all active banners, optionally filtered by position
        with pagination support
        """
        now = datetime.utcnow()
        query = {
            "is_active": True,
            "$or": [
                {"start_date": None},
                {"start_date": {"$lte": now}}
            ],
            "$or": [
                {"end_date": None},
                {"end_date": {"$gte": now}}
            ]
        }
        
        if position:
            query["position"] = position
            
        return await cls.find(query).sort([("priority", -1), ("created_at", -1)]).skip(skip).limit(limit).to_list()

    @classmethod
    async def get_banner_by_position(cls, position: str) -> Optional["Banner"]:
        """
        Get the most recent active banner for a specific position
        """
        now = datetime.utcnow()
        return await cls.find_one(
            {
                "position": position, 
                "is_active": True,
                "$or": [
                    {"start_date": None},
                    {"start_date": {"$lte": now}}
                ],
                "$or": [
                    {"end_date": None},
                    {"end_date": {"$gte": now}}
                ]
            },
            sort=[("priority", -1), ("created_at", -1)]
        )

    @classmethod
    async def count_active_banners(cls, position: Optional[str] = None) -> int:
        """
        Count active banners, optionally filtered by position
        """
        now = datetime.utcnow()
        query = {
            "is_active": True,
            "$or": [
                {"start_date": None},
                {"start_date": {"$lte": now}}
            ],
            "$or": [
                {"end_date": None},
                {"end_date": {"$gte": now}}
            ]
        }
        
        if position:
            query["position"] = position
            
        return await cls.find(query).count()

# Pydantic models for API requests/responses
class BannerBase(BaseModel):
    title: str
    subtitle: Optional[str] = None
    description: Optional[str] = None
    image_url: str
    link: Optional[str] = None
    is_active: bool = True
    position: BannerPosition = BannerPosition.HOME_TOP
    priority: int = 0
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    @validator('end_date')
    def validate_end_date(cls, end_date, values):
        """Validate that end_date is after start_date if both are provided"""
        start_date = values.get('start_date')
        if start_date and end_date and end_date < start_date:
            raise ValueError('end_date must be after start_date')
        return end_date

class BannerCreate(BannerBase):
    pass

class BannerUpdate(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    link: Optional[str] = None
    is_active: Optional[bool] = None
    position: Optional[BannerPosition] = None
    priority: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class BannerResponse(BannerBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class PaginatedBannerResponse(BaseModel):
    """Response model for paginated banner results"""
    items: List[BannerResponse]
    total: int
    page: int
    size: int
    pages: int