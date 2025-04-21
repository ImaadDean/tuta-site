from typing import Optional, List
from datetime import datetime
from uuid import uuid4
from beanie import Document, Link, Indexed
from pydantic import Field, BaseModel, validator
from app.models.user import User

class Review(Document):
    """Review document model for MongoDB using Beanie ODM"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    product_id: str = Indexed()  # Reference to product
    user_id: Optional[str] = None  # Reference to user
    user_name: Optional[str] = None  # Name for non-logged in users
    rating: int  # Rating from 1-5
    content: str  # Review content
    photo_urls: List[str] = []  # Photos uploaded with the review
    verified_purchase: bool = False  # Whether the review is from a verified purchase
    helpful_votes: int = 0  # Number of people who found this review helpful
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    status: str = "published"  # published, pending, rejected
    
    # Define the collection name in MongoDB
    class Settings:
        name = "reviews"
        indexes = [
            "product_id",
            "user_id",
            "rating",
            "created_at",
            "status"
        ]
    
    # Update timestamps on save
    async def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        # Remove update_fields if it's empty to allow all fields to be saved
        if 'update_fields' in kwargs and not kwargs['update_fields']:
            kwargs.pop('update_fields')
        return await super().save(*args, **kwargs)
    
    # Validator for rating to ensure it's between 1 and 5
    @validator('rating')
    def validate_rating(cls, v):
        if v < 1 or v > 5:
            raise ValueError('Rating must be between 1 and 5')
        return v
    
    # Validator for content to ensure it's not empty
    @validator('content')
    def validate_content(cls, v):
        # Allow empty content for special cases like rating-only submissions
        if v is None:
            return ""
        return v
    
    # Method to get user for this review
    async def get_user(self):
        """Get the user for this review"""
        if not self.user_id:
            return None
        return await User.find_one({"id": self.user_id})
    
    # Static methods for getting reviews
    @classmethod
    async def get_by_product(cls, product_id: str) -> List["Review"]:
        """Get reviews for a specific product"""
        return await cls.find({"product_id": product_id, "status": "published"}).sort("-created_at").to_list()
    
    @classmethod
    async def get_by_user(cls, user_id: str) -> List["Review"]:
        """Get reviews from a specific user"""
        return await cls.find({"user_id": user_id, "status": "published"}).sort("-created_at").to_list()
    
    @classmethod
    async def calculate_product_rating(cls, product_id: str) -> dict:
        """Calculate average rating and count for a product"""
        reviews = await cls.find({"product_id": product_id, "status": "published"}).to_list()
        
        if not reviews:
            return {"rating_avg": 0.0, "review_count": 0, "rating_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}}
        
        total_rating = sum(review.rating for review in reviews)
        count = len(reviews)
        
        # Calculate rating distribution
        distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for review in reviews:
            distribution[review.rating] += 1
        
        # Calculate percentages
        percentages = {}
        for rating, count_val in distribution.items():
            percentages[rating] = round((count_val / count) * 100) if count > 0 else 0
        
        # Ensure we return a float with one decimal place for rating_avg
        rating_avg = round(total_rating / count, 1) if count > 0 else 0.0
        
        return {
            "rating_avg": rating_avg,
            "review_count": count,
            "rating_distribution": percentages
        }

# Pydantic models for API
class ReviewBase(BaseModel):
    rating: int
    content: str
    photo_urls: List[str] = []
    
class ReviewCreate(ReviewBase):
    product_id: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    verified_purchase: bool = False

class ReviewUpdate(BaseModel):
    rating: Optional[int] = None
    content: Optional[str] = None
    photo_urls: Optional[List[str]] = None
    helpful_votes: Optional[int] = None
    status: Optional[str] = None

class ReviewResponse(ReviewBase):
    id: str
    product_id: str
    user_id: Optional[str]
    user_name: Optional[str]
    verified_purchase: bool
    helpful_votes: int
    created_at: datetime
    updated_at: Optional[datetime]
    status: str
    
    class Config:
        from_attributes = True 