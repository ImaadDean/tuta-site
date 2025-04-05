from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from uuid import uuid4
from beanie import Document, Link, Indexed
from pydantic import Field, BaseModel, validator
from app.models.scent import Scent

class DiscountActivity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    discount_percentage: float
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    quantity_limit: Optional[int] = None
    items_sold: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    is_active: bool = True

class VariantValue(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    value: str
    price: int  # Main price for this variant
    discount_percentage: Optional[float] = None
    discount_start_date: Optional[datetime] = None
    discount_end_date: Optional[datetime] = None
    discount_quantity_limit: Optional[int] = None
    discount_quantity_used: Optional[int] = None
    discount_activity: List[DiscountActivity] = []

    @validator('discount_percentage')
    def validate_discount_percentage(cls, v):
        if v is not None:
            # Round to 2 decimal places and limit to 2 decimal places
            v = round(v, 2)
        return v

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
        
    def dict(self, *args, **kwargs):
        # Get the base dictionary
        try:
            d = super().dict(*args, **kwargs)
        except AttributeError:
            # If direct dict conversion fails, try other methods or create a new dict
            if hasattr(self, 'model_dump'):
                d = self.model_dump()
            else:
                # Manually create a dictionary with the object's attributes
                d = {}
                for attr in ['id', 'value', 'price', 'discount_percentage', 
                             'discount_start_date', 'discount_end_date',
                             'discount_quantity_limit', 'discount_quantity_used',
                             'discount_activity']:
                    if hasattr(self, attr):
                        value = getattr(self, attr)
                        # Handle MongoDB numbers
                        if isinstance(value, dict) and '$numberInt' in value:
                            value = int(value['$numberInt'])
                        elif isinstance(value, dict) and '$numberDouble' in value:
                            value = float(value['$numberDouble'])
                        # Handle discount_activity list
                        elif attr == 'discount_activity' and isinstance(value, list):
                            # Serialize each DiscountActivity object
                            serialized_activities = []
                            for activity in value:
                                if hasattr(activity, 'dict'):
                                    activity_dict = activity.dict()
                                    # Convert datetime objects
                                    if 'start_date' in activity_dict and isinstance(activity_dict['start_date'], datetime):
                                        activity_dict['start_date'] = activity_dict['start_date'].isoformat()
                                    if 'end_date' in activity_dict and isinstance(activity_dict['end_date'], datetime):
                                        activity_dict['end_date'] = activity_dict['end_date'].isoformat()
                                    if 'created_at' in activity_dict and isinstance(activity_dict['created_at'], datetime):
                                        activity_dict['created_at'] = activity_dict['created_at'].isoformat()
                                    serialized_activities.append(activity_dict)
                                elif isinstance(activity, dict):
                                    serialized_activities.append(activity)
                            value = serialized_activities
                        d[attr] = value
        
        # Convert datetime objects to ISO format strings
        if d.get('discount_start_date'):
            if isinstance(d['discount_start_date'], datetime):
                d['discount_start_date'] = d['discount_start_date'].isoformat()
            elif isinstance(d['discount_start_date'], dict) and '$date' in d['discount_start_date']:
                # Handle MongoDB date format
                date_val = d['discount_start_date']['$date']
                if isinstance(date_val, dict) and '$numberLong' in date_val:
                    timestamp = int(date_val['$numberLong']) / 1000  # MongoDB timestamps are in milliseconds
                    d['discount_start_date'] = datetime.fromtimestamp(timestamp).isoformat()
                else:
                    d['discount_start_date'] = date_val
        
        if d.get('discount_end_date'):
            if isinstance(d['discount_end_date'], datetime):
                d['discount_end_date'] = d['discount_end_date'].isoformat()
            elif isinstance(d['discount_end_date'], dict) and '$date' in d['discount_end_date']:
                # Handle MongoDB date format
                date_val = d['discount_end_date']['$date']
                if isinstance(date_val, dict) and '$numberLong' in date_val:
                    timestamp = int(date_val['$numberLong']) / 1000  # MongoDB timestamps are in milliseconds
                    d['discount_end_date'] = datetime.fromtimestamp(timestamp).isoformat()
                else:
                    d['discount_end_date'] = date_val
        
        # Handle MongoDB price format if needed
        if isinstance(d.get('price'), dict) and '$numberInt' in d['price']:
            d['price'] = int(d['price']['$numberInt'])
            
        # Handle MongoDB discount_percentage format if needed
        if isinstance(d.get('discount_percentage'), dict):
            if '$numberInt' in d['discount_percentage']:
                d['discount_percentage'] = int(d['discount_percentage']['$numberInt'])
            elif '$numberDouble' in d['discount_percentage']:
                d['discount_percentage'] = float(d['discount_percentage']['$numberDouble'])
            
        return d

class Product(Document):
    """
    Product document model for MongoDB using Beanie ODM
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Indexed()  # Correctly indexed field
    short_description: Optional[str] = None
    long_description: Optional[str] = None
    # Removed price field - now using variant pricing only
    stock: int = 0
    in_stock: bool = False
    image_urls: List[str] = []
    category_ids: List[str] = []  # Store references to categories
    brand_id: Optional[str] = None  # Reference to brand
    is_perfume: bool = False  # New field to indicate if product is a perfume
    scent_ids: List[str] = []  # Changed to support multiple scents
    scents: Optional[List[Scent]] = None  # Changed to support multiple scents
    tags: List[str] = []
    status: str = "published"  # published, draft, archived
    featured: bool = False
    is_new: bool = False
    is_bestseller: bool = False
    variants: Dict[str, List[VariantValue]] = {}  # Updated to use VariantValue model
    total_stock_lifetime: int = 0
    in_transit: int = 0
    last_restocked: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    
    # Define the collection name in MongoDB
    class Settings:
        name = "products"
        indexes = [
            "name",
            "status",
            "featured",
            "is_new",
            "is_bestseller",
            "brand_id",
            "category_ids",
            "is_perfume",
            "scent_ids"
        ]
        
    # Define validation and example data
    class Config:
        schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174003",
                "name": "Premium Perfume",
                "short_description": "Luxury fragrance with floral notes",
                "long_description": "Detailed description of the perfume's scent profile...",
                "stock": 100,
                "in_stock": True,
                "image_urls": ["https://example.com/images/perfume1.jpg", "https://example.com/images/perfume2.jpg"],
                "category_ids": ["123e4567-e89b-12d3-a456-426614174000"],
                "brand_id": "123e4567-e89b-12d3-a456-426614174002",
                "is_perfume": True,
                "scent_ids": ["123e4567-e89b-12d3-a456-426614174008"],
                "tags": ["perfume", "fragrance", "luxury"],
                "status": "published",
                "featured": True,
                "variants": {
                    "size": [
                        {"id": "123e4567-e89b-12d3-a456-426614174004", "value": "30ml", "price": 99999},
                        {"id": "123e4567-e89b-12d3-a456-426614174005", "value": "50ml", "price": 149999}
                    ]
                },
                "total_stock_lifetime": 250,
                "in_transit": 50,
                "created_at": "2023-01-01T00:00:00.000Z",
                "updated_at": "2023-01-02T00:00:00.000Z"
            }
        }
    
    # Helper methods for CRUD operations
    @classmethod
    async def get_published_products(cls) -> List["Product"]:
        """Get all published products"""
        return await cls.find({"status": "published"}).to_list()
    
    @classmethod
    async def get_featured_products(cls) -> List["Product"]:
        """Get featured products for homepage display"""
        return await cls.find({"status": "published", "featured": True}).to_list()
    
    @classmethod
    async def get_by_category(cls, category_id: str) -> List["Product"]:
        """Get products by category ID"""
        return await cls.find({"category_ids": category_id, "status": "published"}).to_list()
    
    @classmethod
    async def get_by_brand(cls, brand_id: str) -> List["Product"]:
        """Get products by brand ID"""
        return await cls.find({"brand_id": brand_id, "status": "published"}).to_list()
    
    @classmethod
    async def get_perfumes(cls) -> List["Product"]:
        """Get all perfume products"""
        return await cls.find({"is_perfume": True, "status": "published"}).to_list()
    
    @classmethod
    async def get_by_scent(cls, scent_id: str) -> List["Product"]:
        """Get products by scent ID"""
        return await cls.find({"scent_id": scent_id, "status": "published"}).to_list()
    
    # Update timestamps on save
    async def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return await super().save(*args, **kwargs)
    
    # Method to get categories for this product
    async def get_categories(self) -> List:
        """Get all categories for this product"""
        from app.models.category import Category
        if not self.category_ids:
            return []
        return await Category.find({"id": {"$in": self.category_ids}}).to_list()
    
    # Method to get brand for this product
    async def get_brand(self):
        """Get the brand for this product"""
        if not self.brand_id:
            return None
        from app.models.brand import Brand
        return await Brand.find_one({"id": self.brand_id})
    
    # Method to get scent for this product
    async def get_scent(self):
        """Get the scent for this product"""
        if not self.scent_ids:
            return None
        return await Scent.find({"id": {"$in": self.scent_ids}}).to_list()
    
    # Method to get the minimum price across all variants
    def get_base_price(self) -> int:
        """Get the minimum price across all variants"""
        if not self.variants:
            return 0
            
        min_price = None
        for variant_type, variant_list in self.variants.items():
            for variant in variant_list:
                variant_price = getattr(variant, 'price', 0)
                if min_price is None or variant_price < min_price:
                    min_price = variant_price
        
        return min_price if min_price is not None else 0
    
    # Method to check if product is on sale
    def is_on_sale(self) -> bool:
        """Check if any variant of the product is on sale"""
        if not self.variants:
            return False
            
        now = datetime.now()
        
        for variant_type, variant_list in self.variants.items():
            for variant in variant_list:
                discount = getattr(variant, 'discount_percentage', 0)
                if discount and discount > 0:
                    # Check dates if they exist
                    start_date = getattr(variant, 'discount_start_date', None)
                    end_date = getattr(variant, 'discount_end_date', None)
                    
                    # If no date constraints, it's on sale
                    if not start_date and not end_date:
                        return True
                        
                    # Check start date if set
                    if start_date and now < start_date:
                        continue
                        
                    # Check end date if set
                    if end_date and now > end_date:
                        continue
                        
                    return True
                    
        return False

    def dict(self, *args, **kwargs):
        """
        Custom dictionary serialization to handle MongoDB data structures and variants.
        This ensures all values are JSON serializable.
        """
        try:
            # Get the base dictionary
            d = super().dict(*args, **kwargs)
        except AttributeError:
            # If dict() is not available in parent, try model_dump() or create dict manually
            if hasattr(self, 'model_dump'):
                d = self.model_dump(*args, **kwargs)
            else:
                # Manually create dictionary from the model's attributes
                d = {}
                for key, value in self.__dict__.items():
                    if not key.startswith('_'):
                        d[key] = value
        
        # Ensure the variants are properly serialized
        if 'variants' in d and d['variants']:
            serialized_variants = {}
            for variant_type, variant_list in d['variants'].items():
                serialized_variants[variant_type] = []
                for variant in variant_list:
                    # Handle variant object or dictionary
                    if isinstance(variant, dict):
                        # Already a dict, but may need to ensure MongoDB values are serializable
                        variant_dict = variant
                    else:
                        # Try common serialization methods
                        try:
                            variant_dict = variant.dict() if hasattr(variant, 'dict') else {}
                        except:
                            try:
                                variant_dict = variant.model_dump() if hasattr(variant, 'model_dump') else {}
                            except:
                                # Fallback to manual dict conversion
                                variant_dict = {}
                                for k, v in variant.__dict__.items():
                                    if not k.startswith('_'):
                                        variant_dict[k] = v
                    
                    # Clean up any MongoDB specific types
                    cleaned_variant = {}
                    for k, v in variant_dict.items():
                        # Convert MongoDB date format
                        if isinstance(v, dict) and '$date' in v:
                            if isinstance(v['$date'], dict) and '$numberLong' in v['$date']:
                                cleaned_variant[k] = int(v['$date']['$numberLong']) / 1000
                            else:
                                cleaned_variant[k] = v['$date']
                        # Convert MongoDB integer format
                        elif isinstance(v, dict) and '$numberInt' in v:
                            cleaned_variant[k] = int(v['$numberInt'])
                        # Convert MongoDB long format
                        elif isinstance(v, dict) and '$numberLong' in v:
                            cleaned_variant[k] = int(v['$numberLong'])
                        # Convert MongoDB double format
                        elif isinstance(v, dict) and '$numberDouble' in v:
                            cleaned_variant[k] = float(v['$numberDouble'])
                        else:
                            # Ensure discount_percentage is properly rounded if it's a float
                            if k == 'discount_percentage' and isinstance(v, float):
                                cleaned_variant[k] = round(v, 2)
                            else:
                                cleaned_variant[k] = v
                    
                    serialized_variants[variant_type].append(cleaned_variant)
            
            d['variants'] = serialized_variants
        
        # Add calculated base price for convenience
        d['base_price'] = self.get_base_price()
        
        return d

    # Method to update discount activity when items are sold
    async def update_discount_activity(self, variant_id: str, quantity_sold: int):
        """
        Updates the discount activity record when items are sold
        
        Args:
            variant_id: ID of the variant that was sold
            quantity_sold: Number of items sold
        
        Returns:
            True if updated successfully, False otherwise
        """
        try:
            # Find the variant
            for variant_type, variants in self.variants.items():
                for i, variant in enumerate(variants):
                    variant_id_str = str(variant.id) if hasattr(variant, 'id') else None
                    if variant_id_str == variant_id:
                        # Found the variant, update active discount activity if any
                        if hasattr(variant, 'discount_activity'):
                            for j, activity in enumerate(variant.discount_activity):
                                if hasattr(activity, 'is_active') and activity.is_active:
                                    # Update items sold
                                    current_items_sold = getattr(activity, 'items_sold', 0)
                                    self.variants[variant_type][i].discount_activity[j].items_sold = current_items_sold + quantity_sold
                                    
                                    # Update discount quantity used if limit is set
                                    if hasattr(variant, 'discount_quantity_limit') and variant.discount_quantity_limit:
                                        current_used = getattr(variant, 'discount_quantity_used', 0)
                                        new_used = current_used + quantity_sold
                                        self.variants[variant_type][i].discount_quantity_used = new_used
                                        
                                        # Check if limit reached and deactivate if so
                                        if new_used >= variant.discount_quantity_limit:
                                            print(f"Discount limit reached for variant {variant_id}, deactivating discount")
                                            self.variants[variant_type][i].discount_percentage = None
                                            self.variants[variant_type][i].discount_start_date = None
                                            self.variants[variant_type][i].discount_end_date = None
                                            self.variants[variant_type][i].discount_activity[j].is_active = False
                                    
                                    return True
            
            return False
        except Exception as e:
            print(f"Error updating discount activity: {str(e)}")
            return False

# Pydantic models for API
class ProductBase(BaseModel):
    name: str
    short_description: Optional[str] = None
    long_description: Optional[str] = None
    stock: int = 0
    in_stock: bool = False
    tags: List[str] = []
    status: str = "published"
    featured: bool = False
    is_new: bool = False
    is_bestseller: bool = False
    is_perfume: bool = False
    scent_ids: List[str] = []

class ProductCreate(ProductBase):
    image_urls: List[str] = []
    category_ids: List[str] = []
    brand_id: Optional[str] = None
    variants: Dict[str, List[VariantValue]] = {}

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    short_description: Optional[str] = None
    long_description: Optional[str] = None
    stock: Optional[int] = None
    in_stock: Optional[bool] = None
    image_urls: Optional[List[str]] = None
    category_ids: Optional[List[str]] = None
    brand_id: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None
    featured: Optional[bool] = None
    is_new: Optional[bool] = None
    is_bestseller: Optional[bool] = None
    variants: Optional[Dict[str, List[VariantValue]]] = None
    in_transit: Optional[int] = None
    is_perfume: Optional[bool] = None
    scent_ids: Optional[List[str]] = None

class ProductResponse(ProductBase):
    id: str
    image_urls: List[str]
    category_ids: List[str]
    brand_id: Optional[str]
    variants: Dict[str, List[VariantValue]]
    total_stock_lifetime: int
    in_transit: int
    last_restocked: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]
    
    # Calculate base price and current price based on variants
    base_price: int
    
    @validator('base_price', pre=True, always=True)
    def calculate_base_price(cls, v, values):
        """Calculate the base price from variants"""
        variants = values.get('variants', {})
        if not variants:
            return 0
            
        prices = []
        for variant_type, variant_list in variants.items():
            for variant in variant_list:
                if hasattr(variant, 'price'):
                    prices.append(variant.price)
                elif isinstance(variant, dict) and 'price' in variant:
                    prices.append(variant['price'])
        
        return min(prices) if prices else 0

    class Config:
        from_attributes = True 