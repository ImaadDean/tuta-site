from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from uuid import uuid4
from beanie import Document, Link, Indexed
from pydantic import Field, BaseModel, validator
from app.models.scent import Scent

class DiscountActivity(BaseModel):
    """Model to track discount activity history for product variants"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    discount_percentage: float
    start_date: datetime
    end_date: datetime
    quantity_limit: Optional[int] = None
    items_sold: int = 0
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }

class VariantValue(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    value: str
    price: int
    discount_percentage: Optional[float] = None
    discount_start_date: Optional[datetime] = None
    discount_end_date: Optional[datetime] = None
    discount_quantity_limit: Optional[int] = None
    discount_quantity_used: Optional[int] = None
    discount_activity: List[DiscountActivity] = []

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
                             'discount_start_date', 'discount_end_date']:
                    if hasattr(self, attr):
                        value = getattr(self, attr)
                        # Handle MongoDB numbers
                        if isinstance(value, dict) and '$numberInt' in value:
                            value = int(value['$numberInt'])
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
        if isinstance(d.get('discount_percentage'), dict) and '$numberInt' in d['discount_percentage']:
            d['discount_percentage'] = int(d['discount_percentage']['$numberInt'])

        return d

class Product(Document):
    """
    Product document model for MongoDB using Beanie ODM
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Indexed()  # Correctly indexed field
    short_description: Optional[str] = None
    long_description: Optional[str] = None
    stock: int = 0
    in_stock: bool = False
    view_count: int = 0  # Track product view count
    rating_avg: float = 0.0  # Average product rating
    review_count: int = 0  # Number of reviews
    sale_count: int = 0  # Track number of sales
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
    is_trending: bool = False
    is_top_rated: bool = False
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
            "is_trending",
            "is_top_rated",
            "brand_id",
            "category_ids",
            "is_perfume",
            "scent_ids",
            "view_count",
            "rating_avg",
            "review_count",
            "sale_count",
            "created_at"
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
                "view_count": 0,
                "rating_avg": 4.5,
                "review_count": 42,
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
        return await cls.find({
            "status": "published",
            "$and": [
                {"name": {"$ne": "template"}},
                {"id": {"$not": {"$regex": "template", "$options": "i"}}}
            ]
        }).to_list()

    @classmethod
    async def get_featured_products(cls) -> List["Product"]:
        """Get featured products for homepage display"""
        return await cls.find({
            "status": "published",
            "featured": True,
            "$and": [
                {"name": {"$ne": "template"}},
                {"id": {"$not": {"$regex": "template", "$options": "i"}}}
            ]
        }).to_list()

    @classmethod
    async def get_product_counts(cls):
        """Get counts of products by special status (bestseller, trending, top rated, new arrivals).

        Returns:
            Dict with counts for each product type
        """
        try:
            # Base query for published products
            base_query = {
                "status": "published",
                "$and": [
                    {"name": {"$ne": "template"}},
                    {"id": {"$not": {"$regex": "template", "$options": "i"}}}
                ]
            }

            # Get total count of published products
            total_count = await cls.find(base_query).count()

            # Get count of bestseller products
            bestseller_query = base_query.copy()
            bestseller_query["is_bestseller"] = True
            bestseller_count = await cls.find(bestseller_query).count()

            # Get count of trending products
            trending_query = base_query.copy()
            trending_query["is_trending"] = True
            trending_count = await cls.find(trending_query).count()

            # Get count of top rated products
            top_rated_query = base_query.copy()
            top_rated_query["is_top_rated"] = True
            top_rated_count = await cls.find(top_rated_query).count()

            # Get count of new arrival products
            new_arrival_query = base_query.copy()
            new_arrival_query["is_new"] = True
            new_arrival_count = await cls.find(new_arrival_query).count()

            return {
                "total": total_count,
                "bestsellers": bestseller_count,
                "trending": trending_count,
                "top_rated": top_rated_count,
                "new_arrivals": new_arrival_count
            }
        except Exception as e:
            print(f"Error getting product counts: {str(e)}")
            return {
                "total": 0,
                "bestsellers": 0,
                "trending": 0,
                "top_rated": 0,
                "new_arrivals": 0
            }

    @classmethod
    async def get_bestsellers(cls, limit: int = 8) -> List["Product"]:
        """Get bestseller products for homepage display and other sections.

        Args:
            limit: Maximum number of products to return (default 8)

        Returns:
            List of bestseller products with sale_count > 0, sorted by sale_count
        """
        try:
            # Only get products with sale_count > 0, excluding template products
            print(f"Getting bestsellers with sale_count > 0")
            top_selling = await cls.find(
                {
                    "status": "published",
                    "sale_count": {"$gt": 0},
                    "$and": [
                        {"name": {"$ne": "template"}},
                        {"id": {"$not": {"$regex": "template", "$options": "i"}}}
                    ]
                }
            ).sort([("sale_count", -1)]).limit(limit).to_list()

            print(f"Found {len(top_selling)} products with sale_count > 0")

            # Debug the first few products
            for i, product in enumerate(top_selling[:3]):
                print(f"Product {i+1}: {product.name}, sale_count: {getattr(product, 'sale_count', 0)}")

            # Return only products with sale_count > 0, even if fewer than limit
            print(f"Returning {len(top_selling)} bestseller products with sale_count > 0")
            return top_selling

        except Exception as e:
            # Log the error and return an empty list
            print(f"Error getting bestsellers: {str(e)}")
            return []

    @classmethod
    async def get_by_category(cls, category_id: str) -> List["Product"]:
        """Get products by category ID"""
        return await cls.find({
            "category_ids": category_id,
            "status": "published",
            "$and": [
                {"name": {"$ne": "template"}},
                {"id": {"$not": {"$regex": "template", "$options": "i"}}}
            ]
        }).to_list()

    @classmethod
    async def get_by_brand(cls, brand_id: str) -> List["Product"]:
        """Get products by brand ID"""
        return await cls.find({
            "brand_id": brand_id,
            "status": "published",
            "$and": [
                {"name": {"$ne": "template"}},
                {"id": {"$not": {"$regex": "template", "$options": "i"}}}
            ]
        }).to_list()

    @classmethod
    async def get_perfumes(cls) -> List["Product"]:
        """Get all perfume products"""
        return await cls.find({
            "is_perfume": True,
            "status": "published",
            "$and": [
                {"name": {"$ne": "template"}},
                {"id": {"$not": {"$regex": "template", "$options": "i"}}}
            ]
        }).to_list()

    @classmethod
    async def get_by_scent(cls, scent_id: str) -> List["Product"]:
        """Get products by scent ID"""
        return await cls.find({
            "scent_id": scent_id,
            "status": "published",
            "$and": [
                {"name": {"$ne": "template"}},
                {"id": {"$not": {"$regex": "template", "$options": "i"}}}
            ]
        }).to_list()

    # Update timestamps on save
    async def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return await super().save(*args, **kwargs)

    # Method to increment sale count
    async def increment_sale_count(self, quantity: int = 1):
        """Increment the sale count for this product

        Args:
            quantity: Number of units sold (default 1)
        """
        self.sale_count = getattr(self, "sale_count", 0) + quantity
        await self.save()

    @classmethod
    async def update_all_bestseller_statuses(cls):
        """Update bestseller status for all products based on sale_count.

        This method identifies bestseller products based on their sale_count and
        updates their is_bestseller flag accordingly. A product is considered a
        bestseller if it's in the top 10% of products by sale count or has a sale_count
        above a minimum threshold.

        Returns:
            Tuple[int, int]: Count of bestsellers and non-bestsellers updated
        """
        try:
            # Get all published products, excluding templates
            all_products = await cls.find({
                "status": "published",
                "$and": [
                    {"name": {"$ne": "template"}},
                    {"id": {"$not": {"$regex": "template", "$options": "i"}}}
                ]
            }).to_list()

            if not all_products:
                print("No products found to update bestseller status")
                return 0, 0

            # Sort products by sale_count in descending order
            all_products.sort(key=lambda p: getattr(p, "sale_count", 0), reverse=True)

            # Define thresholds for bestseller status
            min_sale_count = 1  # Minimum sales to be considered a bestseller

            # Set a fixed number of bestsellers (4) as requested
            bestseller_count = 4

            # Track counts for reporting
            updated_bestsellers = 0
            updated_non_bestsellers = 0

            # Update all products
            for i, product in enumerate(all_products):
                sale_count = getattr(product, "sale_count", 0)
                is_bestseller = getattr(product, "is_bestseller", False)

                # Determine if this product should be a bestseller
                should_be_bestseller = (i < bestseller_count) and (sale_count >= min_sale_count)

                # Only update if the status needs to change
                if should_be_bestseller != is_bestseller:
                    product.is_bestseller = should_be_bestseller
                    await product.save()

                    if should_be_bestseller:
                        updated_bestsellers += 1
                        print(f"Marked as bestseller: {product.name} (sale_count: {sale_count})")
                    else:
                        updated_non_bestsellers += 1
                        print(f"Removed bestseller status: {product.name} (sale_count: {sale_count})")

            return updated_bestsellers, updated_non_bestsellers

        except Exception as e:
            print(f"Error updating bestseller statuses: {str(e)}")
            return 0, 0

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

    def get_highest_price(self) -> int:
        """Get the highest price from all variants"""
        highest_price = 0
        if self.variants:
            for variant_values in self.variants.values():
                for variant in variant_values:
                    if hasattr(variant, 'price'):
                        highest_price = max(highest_price, variant.price)
                    elif isinstance(variant, dict) and 'price' in variant:
                        highest_price = max(highest_price, variant['price'])
        return highest_price

    def get_lowest_price(self) -> int:
        """Get the lowest price from all variants"""
        lowest_price = float('inf')
        if self.variants:
            for variant_values in self.variants.values():
                for variant in variant_values:
                    if hasattr(variant, 'price'):
                        lowest_price = min(lowest_price, variant.price)
                    elif isinstance(variant, dict) and 'price' in variant:
                        lowest_price = min(lowest_price, variant['price'])
        return lowest_price if lowest_price != float('inf') else 0

    def get_base_price(self) -> int:
        """Get the base price (highest variant price)"""
        return self.get_highest_price()

    @property
    def base_price(self) -> int:
        """Property to access the base price directly in templates"""
        return self.get_base_price()

    def get_current_price(self) -> int:
        """Get the current price after applying any active discounts"""
        base_price = self.get_highest_price()
        if not self.is_on_sale():
            return base_price

        discounted = base_price * (1 - (self.discount_percentage / 100))
        return round(discounted)

    def is_on_sale(self) -> bool:
        """Check if the product is currently on sale"""
        if not self.discount_percentage or self.discount_percentage <= 0:
            return False

        now = datetime.now()

        # If no date constraints, it's on sale
        if not self.discount_start_date and not self.discount_end_date:
            return True

        # Check start date if set
        if self.discount_start_date and now < self.discount_start_date:
            return False

        # Check end date if set
        if self.discount_end_date and now > self.discount_end_date:
            return False

        return True

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
                            cleaned_variant[k] = v

                    serialized_variants[variant_type].append(cleaned_variant)

            d['variants'] = serialized_variants

        return d

# Pydantic models for API
class ProductBase(BaseModel):
    name: str
    short_description: Optional[str] = None
    long_description: Optional[str] = None
    stock: int = 0
    in_stock: bool = False
    view_count: int = 0  # Track product view count
    rating_avg: float = 0.0  # Average product rating
    review_count: int = 0  # Number of reviews
    sale_count: int = 0  # Track number of sales
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
    view_count: Optional[int] = None
    rating_avg: Optional[float] = None
    review_count: Optional[int] = None
    sale_count: Optional[int] = None
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

    current_price: int

    @validator('current_price', pre=True, always=True)
    def calculate_current_price(cls, v, values):
        """Calculate the current price based on variants and discount"""
        variants = values.get('variants', {})
        highest_price = 0

        # Find highest price from variants
        for variant_values in variants.values():
            for variant in variant_values:
                if hasattr(variant, 'price'):
                    highest_price = max(highest_price, variant.price)
                elif isinstance(variant, dict) and 'price' in variant:
                    highest_price = max(highest_price, variant['price'])

        # Apply discount if any
        discount = values.get('discount_percentage', 0)
        if not discount or discount <= 0:
            return highest_price

        # Calculate discount on integer price
        return int(highest_price * (1 - (discount / 100)))

    class Config:
        from_attributes = True