from fastapi import APIRouter, Depends, HTTPException, status as http_status, Body, Query
from fastapi.responses import JSONResponse
from app.models.user import User
from app.models.message import Message, MessageUser
from app.models.product import Product
from app.models.collection import Collection
from app.models.category import Category
from app.models.banner import Banner, BannerPosition
from app.auth.jwt import get_current_user_optional
from typing import Optional, List, Dict, Any
import logging
import uuid
import json
from datetime import datetime, timedelta
from functools import wraps

# Custom JSON encoder to handle datetime objects
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# Helper function to create JSONResponse with datetime handling
def create_json_response(content: Dict[str, Any], status_code: int = http_status.HTTP_200_OK):
    """Create a JSONResponse with proper datetime serialization"""
    json_content = json.dumps(content, cls=CustomJSONEncoder)
    return JSONResponse(content=json.loads(json_content), status_code=status_code)

# Create router
router = APIRouter(prefix="/api", tags=["client_api"])

# Configure logging
logger = logging.getLogger(__name__)

# Create a timed cache decorator that works with async functions
def timed_cache(seconds: int):
    def wrapper_cache(func):
        cache = {}
        expiration = datetime.now() + timedelta(seconds=seconds)

        @wraps(func)
        async def wrapped_func(*args, **kwargs):
            nonlocal expiration

            # Check if cache needs to be cleared
            if datetime.now() > expiration:
                cache.clear()
                expiration = datetime.now() + timedelta(seconds=seconds)

            # Create a key from the function arguments
            key = str(args) + str(kwargs)

            # Return cached result if available
            if key in cache:
                return cache[key]

            # Call the original function and cache the result
            result = await func(*args, **kwargs)
            cache[key] = result
            return result

        return wrapped_func
    return wrapper_cache

@router.get("/products")
@timed_cache(seconds=30)  # Cache results for 30 seconds
async def get_products(
    status: Optional[str] = Query("published"),
    category_id: Optional[str] = Query(None),
    brand_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    featured: Optional[bool] = Query(None),
    is_new: Optional[bool] = Query(None),
    is_bestseller: Optional[bool] = Query(None),
    min_price: Optional[int] = Query(None),
    max_price: Optional[int] = Query(None),
    limit: int = Query(12, ge=1, le=50),
    skip: int = Query(0, ge=0),
    sort_by: Optional[str] = Query("created_at"),
    sort_order: Optional[str] = Query("desc")
):
    """API endpoint to fetch products for client-side with filtering, search, and pagination"""
    try:
        # Build the query filter
        query_filter = {}

        # Always filter by status for client-side (usually "published")
        query_filter["status"] = status

        # Add category filter if provided
        if category_id:
            query_filter["category_ids"] = category_id

        # Add brand filter if provided
        if brand_id:
            query_filter["brand_id"] = brand_id

        # Add featured filter if provided
        if featured is not None:
            query_filter["featured"] = featured

        # Add new filter if provided
        if is_new is not None:
            query_filter["is_new"] = is_new

        # Add bestseller filter if provided
        if is_bestseller is not None:
            query_filter["is_bestseller"] = is_bestseller

        # Add search filter if provided
        if search:
            # Create a text search query
            query_filter["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"short_description": {"$regex": search, "$options": "i"}},
                {"long_description": {"$regex": search, "$options": "i"}},
                {"tags": {"$regex": search, "$options": "i"}}
            ]

        # Determine sort field and direction
        sort_direction = -1 if sort_order.lower() == "desc" else 1
        sort_field = sort_by if sort_by in ["created_at", "name", "view_count", "rating_avg"] else "created_at"

        # Get products with pagination
        # We might need to fetch more products than requested if we're filtering by price
        fetch_limit = limit * 3 if (min_price is not None or max_price is not None) else limit
        products = await Product.find(query_filter).sort([(sort_field, sort_direction)]).skip(skip).limit(fetch_limit).to_list()

        # Format products for client display
        formatted_products = []
        for product in products:
            try:
                # Get base price (highest variant price)
                base_price = 0
                if hasattr(product, "get_base_price"):
                    base_price = product.get_base_price()

                # Get first image or empty string if no images
                image_url = ""
                if hasattr(product, "image_urls") and product.image_urls and len(product.image_urls) > 0:
                    image_url = product.image_urls[0]

                # Format variants for display - only include the highest price variant
                formatted_variants = []
                highest_price_variant = None
                highest_price = 0

                if hasattr(product, "variants") and product.variants:
                    for variant_type, variant_values in product.variants.items():
                        for variant in variant_values:
                            # Check if variant is a dict or object
                            variant_price = 0
                            variant_value = ""
                            variant_id = ""

                            if isinstance(variant, dict):
                                variant_price = variant.get("price", 0)
                                variant_value = variant.get("value", "")
                                variant_id = variant.get("id", str(uuid.uuid4()))
                            else:
                                variant_price = getattr(variant, "price", 0)
                                variant_value = getattr(variant, "value", "")
                                variant_id = getattr(variant, "id", str(uuid.uuid4()))

                            if variant_price > highest_price:
                                highest_price = variant_price
                                highest_price_variant = {
                                    "id": variant_id,
                                    "type": variant_type,
                                    "value": variant_value,
                                    "price": variant_price,
                                    "display_name": f"{variant_value}"
                                }

                # Create a list with just the highest price variant, or empty if no variants
                formatted_variants = [highest_price_variant] if highest_price_variant else []

                # Calculate if there's a discounted price (old_price vs current_price)
                old_price = None
                current_price = base_price

                # Check if any variant has a discount
                if formatted_variants:
                    for variant in formatted_variants:
                        if variant.get("discount_percentage") and variant.get("discount_percentage") > 0:
                            # Check if discount is active
                            is_discount_active = True

                            # Check date range if provided
                            if variant.get("discount_start_date") and variant.get("discount_end_date"):
                                now = datetime.now()
                                start_date = variant.get("discount_start_date")
                                end_date = variant.get("discount_end_date")

                                if isinstance(start_date, str):
                                    try:
                                        start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                                    except:
                                        start_date = None

                                if isinstance(end_date, str):
                                    try:
                                        end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                                    except:
                                        end_date = None

                                if (start_date and now < start_date) or (end_date and now > end_date):
                                    is_discount_active = False

                            # Check quantity limit if provided
                            if is_discount_active and variant.get("discount_quantity_limit") is not None:
                                discount_limit = variant.get("discount_quantity_limit")
                                used = variant.get("discount_quantity_used") or 0
                                if used >= discount_limit:
                                    is_discount_active = False

                            if is_discount_active:
                                discount_percentage = variant.get("discount_percentage")
                                variant_price = variant.get("price")
                                if variant_price and discount_percentage:
                                    old_price = variant_price
                                    current_price = round(variant_price * (1 - (discount_percentage / 100)))
                                    break

                # Get primary category if available
                primary_category = None
                if hasattr(product, "category_ids") and product.category_ids and len(product.category_ids) > 0:
                    # Just use the first category ID as primary for now
                    primary_category = product.category_ids[0]

                # Add formatted product to results
                formatted_products.append({
                    "id": product.id,
                    "name": product.name,
                    "price": current_price,
                    "old_price": old_price,
                    "image_url": image_url,
                    "image_urls": getattr(product, "image_urls", []),
                    "short_description": getattr(product, "short_description", ""),
                    "long_description": getattr(product, "long_description", ""),
                    "in_stock": getattr(product, "in_stock", False),
                    "stock": getattr(product, "stock", 0),
                    "view_count": getattr(product, "view_count", 0),
                    "rating_avg": getattr(product, "rating_avg", 0),
                    "review_count": getattr(product, "review_count", 0),
                    "featured": getattr(product, "featured", False),
                    "is_new": getattr(product, "is_new", False),
                    "is_bestseller": getattr(product, "is_bestseller", False),
                    "new": getattr(product, "is_new", False),  # Duplicate for template compatibility
                    "bestseller": getattr(product, "is_bestseller", False),  # Duplicate for template compatibility
                    "category": primary_category,
                    "category_ids": getattr(product, "category_ids", []),
                    "brand_id": getattr(product, "brand_id", None),
                    "tags": getattr(product, "tags", []),
                    "variants": formatted_variants,
                    "has_variants": len(formatted_variants) > 0,
                    "created_at": getattr(product, "created_at", None),
                    "updated_at": getattr(product, "updated_at", None)
                })
            except Exception as e:
                # Log the error but continue processing other products
                logger.error(f"Error formatting product {getattr(product, 'id', 'unknown')}: {str(e)}")
                continue

        # Apply price filtering if needed
        if min_price is not None or max_price is not None:
            filtered_products = []
            for product in formatted_products:
                product_price = product["price"]

                # Check if price is within the specified range
                price_in_range = True
                if min_price is not None and product_price < min_price:
                    price_in_range = False
                if max_price is not None and product_price > max_price:
                    price_in_range = False

                if price_in_range:
                    filtered_products.append(product)

            # Replace the formatted products with the filtered ones
            formatted_products = filtered_products[:limit]

            # Adjust total count for pagination
            total_count = len(filtered_products)
        else:
            # Get total count for pagination if no price filtering
            total_count = await Product.find(query_filter).count()

        # Return formatted response
        return create_json_response(
            {
                "success": True,
                "products": formatted_products,
                "pagination": {
                    "total": total_count,
                    "limit": limit,
                    "skip": skip,
                    "has_more": (skip + limit) < total_count
                }
            },
            http_status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Error fetching products: {str(e)}")
        return create_json_response(
            {
                "success": False,
                "message": "An error occurred while fetching products"
            },
            http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# Get new arrivals (most recently created products)
@router.get("/products/new-arrivals")
@timed_cache(seconds=60)  # Cache results for 60 seconds
async def get_new_arrivals(
    limit: int = Query(8, ge=1, le=20)
):
    """API endpoint to fetch new arrivals (most recently created products)"""
    try:
        # Get products sorted by creation date (newest first)
        query_filter = {"status": "published"}
        products = await Product.find(query_filter).sort([("created_at", -1)]).limit(limit).to_list()

        # Format products for client display
        formatted_products = []
        for product in products:
            try:
                # Get base price (highest variant price)
                base_price = 0
                if hasattr(product, "get_base_price"):
                    base_price = product.get_base_price()

                # Get first image or empty string if no images
                image_url = ""
                if hasattr(product, "image_urls") and product.image_urls and len(product.image_urls) > 0:
                    image_url = product.image_urls[0]

                # Format variants for display - only include the highest price variant
                formatted_variants = []
                highest_price_variant = None
                highest_price = 0

                if hasattr(product, "variants") and product.variants:
                    for variant_type, variant_values in product.variants.items():
                        for variant in variant_values:
                            # Check if variant is a dict or object
                            variant_price = 0
                            variant_value = ""
                            variant_id = ""

                            if isinstance(variant, dict):
                                variant_price = variant.get("price", 0)
                                variant_value = variant.get("value", "")
                                variant_id = variant.get("id", str(uuid.uuid4()))
                            else:
                                variant_price = getattr(variant, "price", 0)
                                variant_value = getattr(variant, "value", "")
                                variant_id = getattr(variant, "id", str(uuid.uuid4()))

                            if variant_price > highest_price:
                                highest_price = variant_price
                                highest_price_variant = {
                                    "id": variant_id,
                                    "type": variant_type,
                                    "value": variant_value,
                                    "price": variant_price,
                                    "display_name": f"{variant_value}"
                                }

                # Create a list with just the highest price variant, or empty if no variants
                formatted_variants = [highest_price_variant] if highest_price_variant else []

                # Calculate if there's a discounted price
                old_price = None
                current_price = base_price

                # Check if any variant has a discount
                if formatted_variants:
                    for variant in formatted_variants:
                        if variant.get("discount_percentage") and variant.get("discount_percentage") > 0:
                            discount_percentage = variant.get("discount_percentage")
                            variant_price = variant.get("price")
                            if variant_price and discount_percentage:
                                old_price = variant_price
                                current_price = round(variant_price * (1 - (discount_percentage / 100)))
                                break

                # Get primary category if available
                primary_category = None
                if hasattr(product, "category_ids") and product.category_ids and len(product.category_ids) > 0:
                    # Just use the first category ID as primary for now
                    primary_category = product.category_ids[0]

                # Add formatted product to results
                formatted_products.append({
                    "id": product.id,
                    "name": product.name,
                    "price": current_price,
                    "old_price": old_price,
                    "image_url": image_url,
                    "image_urls": getattr(product, "image_urls", []),
                    "short_description": getattr(product, "short_description", ""),
                    "in_stock": getattr(product, "in_stock", False),
                    "stock": getattr(product, "stock", 0),
                    "view_count": getattr(product, "view_count", 0),
                    "rating_avg": getattr(product, "rating_avg", 0),
                    "review_count": getattr(product, "review_count", 0),
                    "featured": getattr(product, "featured", False),
                    "is_new": getattr(product, "is_new", False),
                    "is_bestseller": getattr(product, "is_bestseller", False),
                    "new": getattr(product, "is_new", False),  # Duplicate for template compatibility
                    "bestseller": getattr(product, "is_bestseller", False),  # Duplicate for template compatibility
                    "category": primary_category,
                    "variants": formatted_variants,
                    "has_variants": len(formatted_variants) > 0,
                    "created_at": getattr(product, "created_at", None)
                })
            except Exception as e:
                # Log the error but continue processing other products
                logger.error(f"Error formatting product {getattr(product, 'id', 'unknown')}: {str(e)}")
                continue

        return create_json_response(
            {
                "success": True,
                "new_arrivals": formatted_products
            },
            http_status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Error fetching new arrivals: {str(e)}")
        return create_json_response(
            {
                "success": False,
                "message": "An error occurred while fetching new arrivals"
            },
            http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# Get trending products (highest view count)
@router.get("/products/trending")
@timed_cache(seconds=60)  # Cache results for 60 seconds
async def get_trending_products(
    limit: int = Query(8, ge=1, le=20)
):
    """API endpoint to fetch trending products (highest view count)"""
    try:
        # Get products sorted by view count (highest first)
        query_filter = {"status": "published"}
        products = await Product.find(query_filter).sort([("view_count", -1)]).limit(limit).to_list()

        # Format products for client display
        formatted_products = []
        for product in products:
            try:
                # Get base price (highest variant price)
                base_price = 0
                if hasattr(product, "get_base_price"):
                    base_price = product.get_base_price()

                # Get first image or empty string if no images
                image_url = ""
                if hasattr(product, "image_urls") and product.image_urls and len(product.image_urls) > 0:
                    image_url = product.image_urls[0]

                # Format variants for display - only include the highest price variant
                formatted_variants = []
                highest_price_variant = None
                highest_price = 0

                if hasattr(product, "variants") and product.variants:
                    for variant_type, variant_values in product.variants.items():
                        for variant in variant_values:
                            # Check if variant is a dict or object
                            variant_price = 0
                            variant_value = ""
                            variant_id = ""

                            if isinstance(variant, dict):
                                variant_price = variant.get("price", 0)
                                variant_value = variant.get("value", "")
                                variant_id = variant.get("id", str(uuid.uuid4()))
                            else:
                                variant_price = getattr(variant, "price", 0)
                                variant_value = getattr(variant, "value", "")
                                variant_id = getattr(variant, "id", str(uuid.uuid4()))

                            if variant_price > highest_price:
                                highest_price = variant_price
                                highest_price_variant = {
                                    "id": variant_id,
                                    "type": variant_type,
                                    "value": variant_value,
                                    "price": variant_price,
                                    "display_name": f"{variant_value}"
                                }

                # Create a list with just the highest price variant, or empty if no variants
                formatted_variants = [highest_price_variant] if highest_price_variant else []

                # Calculate if there's a discounted price
                old_price = None
                current_price = base_price

                # Check if any variant has a discount
                if formatted_variants:
                    for variant in formatted_variants:
                        if variant.get("discount_percentage") and variant.get("discount_percentage") > 0:
                            discount_percentage = variant.get("discount_percentage")
                            variant_price = variant.get("price")
                            if variant_price and discount_percentage:
                                old_price = variant_price
                                current_price = round(variant_price * (1 - (discount_percentage / 100)))
                                break

                # Get primary category if available
                primary_category = None
                if hasattr(product, "category_ids") and product.category_ids and len(product.category_ids) > 0:
                    # Just use the first category ID as primary for now
                    primary_category = product.category_ids[0]

                # Add formatted product to results
                formatted_products.append({
                    "id": product.id,
                    "name": product.name,
                    "price": current_price,
                    "old_price": old_price,
                    "image_url": image_url,
                    "image_urls": getattr(product, "image_urls", []),
                    "short_description": getattr(product, "short_description", ""),
                    "in_stock": getattr(product, "in_stock", False),
                    "stock": getattr(product, "stock", 0),
                    "view_count": getattr(product, "view_count", 0),
                    "rating_avg": getattr(product, "rating_avg", 0),
                    "review_count": getattr(product, "review_count", 0),
                    "featured": getattr(product, "featured", False),
                    "is_new": getattr(product, "is_new", False),
                    "is_bestseller": getattr(product, "is_bestseller", False),
                    "new": getattr(product, "is_new", False),  # Duplicate for template compatibility
                    "bestseller": getattr(product, "is_bestseller", False),  # Duplicate for template compatibility
                    "category": primary_category,
                    "variants": formatted_variants,
                    "has_variants": len(formatted_variants) > 0,
                    "created_at": getattr(product, "created_at", None)
                })
            except Exception as e:
                # Log the error but continue processing other products
                logger.error(f"Error formatting product {getattr(product, 'id', 'unknown')}: {str(e)}")
                continue

        return create_json_response(
            {
                "success": True,
                "trending_products": formatted_products
            },
            http_status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Error fetching trending products: {str(e)}")
        return create_json_response(
            {
                "success": False,
                "message": "An error occurred while fetching trending products"
            },
            http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# Get top rated products (highest rating)
@router.get("/products/top-rated")
@timed_cache(seconds=60)  # Cache results for 60 seconds
async def get_top_rated_products(
    limit: int = Query(8, ge=1, le=20)
):
    """API endpoint to fetch top rated products (highest rating)"""
    try:
        # Get products sorted by rating (highest first)
        query_filter = {"status": "published", "rating_avg": {"$gt": 0}}
        products = await Product.find(query_filter).sort([("rating_avg", -1)]).limit(limit).to_list()

        # Format products for client display
        formatted_products = []
        for product in products:
            try:
                # Get base price (highest variant price)
                base_price = 0
                if hasattr(product, "get_base_price"):
                    base_price = product.get_base_price()

                # Get first image or empty string if no images
                image_url = ""
                if hasattr(product, "image_urls") and product.image_urls and len(product.image_urls) > 0:
                    image_url = product.image_urls[0]

                # Format variants for display - only include the highest price variant
                formatted_variants = []
                highest_price_variant = None
                highest_price = 0

                if hasattr(product, "variants") and product.variants:
                    for variant_type, variant_values in product.variants.items():
                        for variant in variant_values:
                            # Check if variant is a dict or object
                            variant_price = 0
                            variant_value = ""
                            variant_id = ""

                            if isinstance(variant, dict):
                                variant_price = variant.get("price", 0)
                                variant_value = variant.get("value", "")
                                variant_id = variant.get("id", str(uuid.uuid4()))
                            else:
                                variant_price = getattr(variant, "price", 0)
                                variant_value = getattr(variant, "value", "")
                                variant_id = getattr(variant, "id", str(uuid.uuid4()))

                            if variant_price > highest_price:
                                highest_price = variant_price
                                highest_price_variant = {
                                    "id": variant_id,
                                    "type": variant_type,
                                    "value": variant_value,
                                    "price": variant_price,
                                    "display_name": f"{variant_value}"
                                }

                # Create a list with just the highest price variant, or empty if no variants
                formatted_variants = [highest_price_variant] if highest_price_variant else []

                # Calculate if there's a discounted price
                old_price = None
                current_price = base_price

                # Check if any variant has a discount
                if formatted_variants:
                    for variant in formatted_variants:
                        if variant.get("discount_percentage") and variant.get("discount_percentage") > 0:
                            discount_percentage = variant.get("discount_percentage")
                            variant_price = variant.get("price")
                            if variant_price and discount_percentage:
                                old_price = variant_price
                                current_price = round(variant_price * (1 - (discount_percentage / 100)))
                                break

                # Get primary category if available
                primary_category = None
                if hasattr(product, "category_ids") and product.category_ids and len(product.category_ids) > 0:
                    # Just use the first category ID as primary for now
                    primary_category = product.category_ids[0]

                # Add formatted product to results
                formatted_products.append({
                    "id": product.id,
                    "name": product.name,
                    "price": current_price,
                    "old_price": old_price,
                    "image_url": image_url,
                    "image_urls": getattr(product, "image_urls", []),
                    "short_description": getattr(product, "short_description", ""),
                    "in_stock": getattr(product, "in_stock", False),
                    "stock": getattr(product, "stock", 0),
                    "view_count": getattr(product, "view_count", 0),
                    "rating_avg": getattr(product, "rating_avg", 0),
                    "review_count": getattr(product, "review_count", 0),
                    "featured": getattr(product, "featured", False),
                    "is_new": getattr(product, "is_new", False),
                    "is_bestseller": getattr(product, "is_bestseller", False),
                    "new": getattr(product, "is_new", False),  # Duplicate for template compatibility
                    "bestseller": getattr(product, "is_bestseller", False),  # Duplicate for template compatibility
                    "category": primary_category,
                    "variants": formatted_variants,
                    "has_variants": len(formatted_variants) > 0,
                    "created_at": getattr(product, "created_at", None)
                })
            except Exception as e:
                # Log the error but continue processing other products
                logger.error(f"Error formatting product {getattr(product, 'id', 'unknown')}: {str(e)}")
                continue

        return create_json_response(
            {
                "success": True,
                "top_rated_products": formatted_products
            },
            http_status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Error fetching top rated products: {str(e)}")
        return create_json_response(
            {
                "success": False,
                "message": "An error occurred while fetching top rated products"
            },
            http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@router.get("/products/{product_id}")
async def get_product_by_id(
    product_id: str
):
    """API endpoint to fetch a single product by ID"""
    try:
        # Try to find product using multiple id fields
        product = await Product.find_one({"$or": [{"id": product_id}, {"_id": product_id}]})

        if not product:
            return create_json_response(
                {
                    "success": False,
                    "message": "Product not found"
                },
                http_status.HTTP_404_NOT_FOUND
            )

        # Get base price (highest variant price)
        base_price = product.get_base_price() if hasattr(product, "get_base_price") else 0

        # Format variants for display - only include the highest price variant
        formatted_variants = []
        highest_price_variant = None
        highest_price = 0

        if hasattr(product, "variants") and product.variants:
            for variant_type, variant_values in product.variants.items():
                for variant in variant_values:
                    # Check if variant is a dict or object
                    variant_price = 0
                    variant_value = ""
                    variant_id = ""

                    if isinstance(variant, dict):
                        variant_price = variant.get("price", 0)
                        variant_value = variant.get("value", "")
                        variant_id = variant.get("id", str(uuid.uuid4()))
                    else:
                        variant_price = getattr(variant, "price", 0)
                        variant_value = getattr(variant, "value", "")
                        variant_id = getattr(variant, "id", str(uuid.uuid4()))

                    if variant_price > highest_price:
                        highest_price = variant_price
                        highest_price_variant = {
                            "id": variant_id,
                            "type": variant_type,
                            "value": variant_value,
                            "price": variant_price,
                            "display_name": f"{variant_value}"
                        }

        # Create a list with just the highest price variant, or empty if no variants
        formatted_variants = [highest_price_variant] if highest_price_variant else []

        # Increment view count
        product.view_count = getattr(product, "view_count", 0) + 1
        await product.save()

        # Calculate if there's a discounted price (old_price vs current_price)
        old_price = None
        current_price = base_price

        # Check if any variant has a discount
        if formatted_variants:
            for variant in formatted_variants:
                if variant.get("discount_percentage") and variant.get("discount_percentage") > 0:
                    # Check if discount is active
                    is_discount_active = True

                    # Check date range if provided
                    if variant.get("discount_start_date") and variant.get("discount_end_date"):
                        now = datetime.now()
                        start_date = variant.get("discount_start_date")
                        end_date = variant.get("discount_end_date")

                        if isinstance(start_date, str):
                            try:
                                start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                            except:
                                start_date = None

                        if isinstance(end_date, str):
                            try:
                                end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                            except:
                                end_date = None

                        if (start_date and now < start_date) or (end_date and now > end_date):
                            is_discount_active = False

                    # Check quantity limit if provided
                    if is_discount_active and variant.get("discount_quantity_limit") is not None:
                        limit = variant.get("discount_quantity_limit")
                        used = variant.get("discount_quantity_used") or 0
                        if used >= limit:
                            is_discount_active = False

                    if is_discount_active:
                        discount_percentage = variant.get("discount_percentage")
                        variant_price = variant.get("price")
                        if variant_price and discount_percentage:
                            old_price = variant_price
                            current_price = round(variant_price * (1 - (discount_percentage / 100)))
                            break

        # Get primary category if available
        primary_category = None
        if hasattr(product, "category_ids") and product.category_ids and len(product.category_ids) > 0:
            # Just use the first category ID as primary for now
            primary_category = product.category_ids[0]

        # Format product for response
        formatted_product = {
            "id": product.id,
            "name": product.name,
            "price": current_price,
            "old_price": old_price,
            "image_url": product.image_urls[0] if product.image_urls else "",
            "image_urls": product.image_urls,
            "short_description": getattr(product, "short_description", ""),
            "long_description": getattr(product, "long_description", ""),
            "in_stock": getattr(product, "in_stock", False),
            "stock": getattr(product, "stock", 0),
            "view_count": getattr(product, "view_count", 0),
            "rating_avg": getattr(product, "rating_avg", 0),
            "review_count": getattr(product, "review_count", 0),
            "featured": getattr(product, "featured", False),
            "is_new": getattr(product, "is_new", False),
            "is_bestseller": getattr(product, "is_bestseller", False),
            "new": getattr(product, "is_new", False),  # Duplicate for template compatibility
            "bestseller": getattr(product, "is_bestseller", False),  # Duplicate for template compatibility
            "category": primary_category,
            "variants": formatted_variants,
            "has_variants": len(formatted_variants) > 0,
            "brand_id": getattr(product, "brand_id", None),
            "category_ids": getattr(product, "category_ids", []),
            "tags": getattr(product, "tags", []),
            "created_at": getattr(product, "created_at", None),
            "updated_at": getattr(product, "updated_at", None)
        }

        return create_json_response(
            {
                "success": True,
                "product": formatted_product
            },
            http_status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Error fetching product {product_id}: {str(e)}")
        return create_json_response(
            {
                "success": False,
                "message": "An error occurred while fetching the product"
            },
            http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@router.get("/collections")
@timed_cache(seconds=600)  # Cache results for 10 minutes
async def get_collections(
    active_only: bool = Query(True),
    featured_only: bool = Query(False),
    with_categories: bool = Query(False),
    limit: int = Query(None)
):
    """API endpoint to fetch collections

    Args:
        active_only: Only return active collections
        featured_only: Only return featured collections
        with_categories: Include categories for each collection
        limit: Maximum number of collections to return
    """
    try:
        # Build query based on parameters
        query = {}
        if active_only:
            query["is_active"] = True
        if featured_only:
            query["is_featured"] = True

        # Get collections
        collections_query = Collection.find(query).sort("order")
        if limit:
            collections_query = collections_query.limit(limit)

        collections = await collections_query.to_list()

        # Format collections for response
        formatted_collections = []
        for collection in collections:
            collection_data = {
                "id": collection.id,
                "name": collection.name,
                "description": collection.description,
                "image_url": collection.image_url,
                "is_active": collection.is_active,
                "is_featured": collection.is_featured,
                "order": collection.order
            }

            # Include categories if requested
            if with_categories:
                categories = await collection.get_categories()
                collection_data["categories"] = [
                    {
                        "id": category.id,
                        "name": category.name,
                        "description": category.description,
                        "icon_url": category.icon_url,
                        "product_count": category.product_count,
                        "is_active": category.is_active
                    }
                    for category in categories
                ]

            formatted_collections.append(collection_data)

        return create_json_response(
            {
                "success": True,
                "collections": formatted_collections
            },
            http_status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Error fetching collections: {str(e)}")
        return create_json_response(
            {
                "success": False,
                "message": "An error occurred while fetching collections"
            },
            http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@router.get("/banners")
@timed_cache(seconds=600)  # Cache results for 10 minutes
async def get_banners(
    position: Optional[str] = Query(None, description="Filter banners by position"),
    active_only: bool = Query(True, description="Only return active banners"),
    limit: int = Query(10, ge=1, le=20, description="Maximum number of banners to return")
):
    """API endpoint to fetch banners

    Args:
        position: Filter banners by position (e.g., home_top, category_page)
        active_only: Only return active banners
        limit: Maximum number of banners to return
    """
    try:
        # Get banners based on parameters
        if active_only:
            # Use the model's method to get active banners
            if position:
                banners = await Banner.get_active_banners(position=position, limit=limit)
            else:
                banners = await Banner.get_active_banners(limit=limit)
        else:
            # Build a custom query
            query = {}
            if position:
                query["position"] = position

            banners = await Banner.find(query).sort([("priority", -1), ("created_at", -1)]).limit(limit).to_list()

        # Format banners for response
        formatted_banners = []
        for banner in banners:
            formatted_banners.append({
                "id": banner.id,
                "title": banner.title,
                "subtitle": banner.subtitle,
                "description": banner.description,
                "image_url": banner.image_url,
                "link": banner.link,
                "position": banner.position,
                "priority": banner.priority
            })

        return create_json_response(
            {
                "success": True,
                "banners": formatted_banners,
                "total": len(formatted_banners)
            },
            http_status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Error fetching banners: {str(e)}")
        return create_json_response(
            {
                "success": False,
                "message": "An error occurred while fetching banners"
            },
            http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@router.get("/categories")
@timed_cache(seconds=600)  # Cache results for 10 minutes
async def get_all_categories(
    active_only: bool = Query(True),
    with_collection: bool = Query(False),
    limit: int = Query(None)
):
    """API endpoint to fetch all categories

    Args:
        active_only: Only return active categories
        with_collection: Include collection data for each category
        limit: Maximum number of categories to return
    """
    try:
        # Build query based on parameters
        query = {}
        if active_only:
            query["is_active"] = True

        # Get categories
        categories_query = Category.find(query).sort("name")
        if limit:
            categories_query = categories_query.limit(limit)

        categories = await categories_query.to_list()

        # Format categories for response
        formatted_categories = []
        for category in categories:
            category_data = {
                "id": category.id,
                "name": category.name,
                "description": category.description,
                "icon_url": category.icon_url,
                "product_count": category.product_count,
                "is_active": category.is_active,
                "collection_id": category.collection_id
            }

            # Include collection data if requested
            if with_collection and category.collection_id:
                collection = await Collection.find_one({"id": category.collection_id})
                if collection:
                    category_data["collection"] = {
                        "id": collection.id,
                        "name": collection.name,
                        "image_url": collection.image_url,
                        "is_active": collection.is_active
                    }

            formatted_categories.append(category_data)

        return create_json_response(
            {
                "success": True,
                "categories": formatted_categories,
                "total": len(formatted_categories)
            },
            http_status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Error fetching categories: {str(e)}")
        return create_json_response(
            {
                "success": False,
                "message": "An error occurred while fetching categories"
            },
            http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@router.get("/collections/{collection_id}/categories")
@timed_cache(seconds=600)  # Cache results for 10 minutes
async def get_collection_categories(
    collection_id: str
):
    """API endpoint to fetch categories for a specific collection

    Args:
        collection_id: ID of the collection to get categories for
    """
    try:
        # Get the collection
        collection = await Collection.find_one({"_id": collection_id})
        if not collection:
            return create_json_response(
                {
                    "success": False,
                    "message": f"Collection with ID {collection_id} not found"
                },
                http_status.HTTP_404_NOT_FOUND
            )

        # Get categories for this collection
        categories = await Category.find({"collection_id": collection_id, "is_active": True}).to_list()

        # Format categories for response
        formatted_categories = []
        for category in categories:
            formatted_categories.append({
                "id": category.id,
                "name": category.name,
                "description": category.description,
                "icon_url": category.icon_url,
                "product_count": category.product_count,
                "is_active": category.is_active
            })

        return create_json_response(
            {
                "success": True,
                "collection_id": collection_id,
                "collection_name": collection.name,
                "categories": formatted_categories
            },
            http_status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Error fetching categories for collection {collection_id}: {str(e)}")
        return create_json_response(
            {
                "success": False,
                "message": "An error occurred while fetching categories"
            },
            http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@router.get("/banners/position/{position}")
@timed_cache(seconds=300)  # Cache results for 5 minutes
async def get_banners_by_position(
    position: str,
    limit: int = Query(5, ge=1, le=10, description="Maximum number of banners to return")
):
    """API endpoint to fetch banners by position

    Args:
        position: Banner position (e.g., home_top, category_page)
        limit: Maximum number of banners to return
    """
    try:
        # Get active banners for the specified position
        banners = await Banner.get_active_banners(position=position, limit=limit)

        # Format banners for response
        formatted_banners = []
        for banner in banners:
            formatted_banners.append({
                "id": banner.id,
                "title": banner.title,
                "subtitle": banner.subtitle,
                "description": banner.description,
                "image_url": banner.image_url,
                "link": banner.link,
                "position": banner.position,
                "priority": banner.priority
            })

        return create_json_response(
            {
                "success": True,
                "position": position,
                "banners": formatted_banners,
                "total": len(formatted_banners)
            },
            http_status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Error fetching banners for position {position}: {str(e)}")
        return create_json_response(
            {
                "success": False,
                "message": "An error occurred while fetching banners"
            },
            http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.get("/banners/{banner_id}")
@timed_cache(seconds=600)  # Cache results for 10 minutes
async def get_banner_by_id(
    banner_id: str
):
    """API endpoint to fetch a specific banner by ID

    Args:
        banner_id: ID of the banner to get
    """
    try:
        # Get the banner
        banner = await Banner.find_one({"id": banner_id})
        if not banner:
            return create_json_response(
                {
                    "success": False,
                    "message": f"Banner with ID {banner_id} not found"
                },
                http_status.HTTP_404_NOT_FOUND
            )

        # Format banner for response
        banner_data = {
            "id": banner.id,
            "title": banner.title,
            "subtitle": banner.subtitle,
            "description": banner.description,
            "image_url": banner.image_url,
            "link": banner.link,
            "position": banner.position,
            "priority": banner.priority,
            "is_active": banner.is_active,
            "start_date": banner.start_date.isoformat() if banner.start_date else None,
            "end_date": banner.end_date.isoformat() if banner.end_date else None,
            "created_at": banner.created_at.isoformat(),
            "updated_at": banner.updated_at.isoformat()
        }

        return create_json_response(
            {
                "success": True,
                "banner": banner_data
            },
            http_status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Error fetching banner {banner_id}: {str(e)}")
        return create_json_response(
            {
                "success": False,
                "message": "An error occurred while fetching the banner"
            },
            http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@router.get("/categories/{category_id}")
@timed_cache(seconds=600)  # Cache results for 10 minutes
async def get_category_by_id(
    category_id: str,
    with_collection: bool = Query(False),
    with_products: bool = Query(False),
    products_limit: int = Query(10)
):
    """API endpoint to fetch a specific category by ID

    Args:
        category_id: ID of the category to get
        with_collection: Include collection data for the category
        with_products: Include products in this category
        products_limit: Maximum number of products to return if with_products is True
    """
    try:
        # Get the category
        category = await Category.find_one({"id": category_id})
        if not category:
            return create_json_response(
                {
                    "success": False,
                    "message": f"Category with ID {category_id} not found"
                },
                http_status.HTTP_404_NOT_FOUND
            )

        # Format category for response
        category_data = {
            "id": category.id,
            "name": category.name,
            "description": category.description,
            "icon_url": category.icon_url,
            "product_count": category.product_count,
            "is_active": category.is_active,
            "collection_id": category.collection_id
        }

        # Include collection data if requested
        if with_collection and category.collection_id:
            collection = await Collection.find_one({"id": category.collection_id})
            if collection:
                category_data["collection"] = {
                    "id": collection.id,
                    "name": collection.name,
                    "image_url": collection.image_url,
                    "is_active": collection.is_active
                }

        # Include products if requested
        if with_products:
            products = await Product.find({"category_id": category_id, "status": "published"}).limit(products_limit).to_list()

            # Format products for response
            formatted_products = []
            for product in products:
                # Ensure we have at least one image
                image_urls = product.image_urls if product.image_urls else ["/static/images/product-placeholder.jpg"]

                formatted_products.append({
                    "id": product.id,
                    "name": product.name,
                    "description": product.description,
                    "price": product.price,
                    "old_price": product.old_price,
                    "image_urls": image_urls,
                    "rating_avg": getattr(product, "rating_avg", 0),
                    "review_count": getattr(product, "review_count", 0),
                    "stock": getattr(product, "stock", 0),
                    "sale_count": getattr(product, "sale_count", 0),
                    "in_stock": product.stock > 0 if hasattr(product, "stock") else True
                })

            category_data["products"] = formatted_products

        return create_json_response(
            {
                "success": True,
                "category": category_data
            },
            http_status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Error fetching category {category_id}: {str(e)}")
        return create_json_response(
            {
                "success": False,
                "message": "An error occurred while fetching the category"
            },
            http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@router.get("/bestseller-products")
@timed_cache(seconds=300)  # Cache results for 5 minutes
async def get_bestseller_products(
    limit: int = Query(8, ge=1, le=20)
):
    """API endpoint to fetch bestseller products for homepage based on sale_count > 0"""
    try:
        # Get bestseller products using the dedicated method
        bestseller_products = await Product.get_bestsellers(limit=limit)

        # Log the number of bestseller products found
        logger.info(f"Found {len(bestseller_products)} bestseller products with sale_count > 0")

        # Format products for response
        formatted_products = []
        for product in bestseller_products:
            # Get base price
            base_price = product.get_base_price() if hasattr(product, "get_base_price") else 0

            # Get first image
            image_url = product.image_urls[0] if product.image_urls else ""

            # Format variants for display - only include the highest price variant
            formatted_variants = []
            highest_price_variant = None
            highest_price = 0

            if hasattr(product, "variants") and product.variants:
                for variant_type, variant_values in product.variants.items():
                    for variant in variant_values:
                        # Check if variant is a dict or object
                        variant_price = 0
                        variant_value = ""
                        variant_id = ""

                        if isinstance(variant, dict):
                            variant_price = variant.get("price", 0)
                            variant_value = variant.get("value", "")
                            variant_id = variant.get("id", str(uuid.uuid4()))
                        else:
                            variant_price = getattr(variant, "price", 0)
                            variant_value = getattr(variant, "value", "")
                            variant_id = getattr(variant, "id", str(uuid.uuid4()))

                        if variant_price > highest_price:
                            highest_price = variant_price
                            highest_price_variant = {
                                "id": variant_id,
                                "type": variant_type,
                                "value": variant_value,
                                "price": variant_price,
                                "display_name": f"{variant_value}"
                            }

            # Create a list with just the highest price variant, or empty if no variants
            formatted_variants = [highest_price_variant] if highest_price_variant else []

            # Calculate if there's a discounted price
            old_price = None
            current_price = base_price

            # Check if any variant has a discount
            if formatted_variants:
                for variant in formatted_variants:
                    if variant.get("discount_percentage") and variant.get("discount_percentage") > 0:
                        discount_percentage = variant.get("discount_percentage")
                        variant_price = variant.get("price")
                        if variant_price and discount_percentage:
                            old_price = variant_price
                            current_price = round(variant_price * (1 - (discount_percentage / 100)))
                            break

            # Get primary category if available
            primary_category = None
            if hasattr(product, "category_ids") and product.category_ids and len(product.category_ids) > 0:
                # Just use the first category ID as primary for now
                primary_category = product.category_ids[0]

            formatted_products.append({
                "id": product.id,
                "name": product.name,
                "price": current_price,
                "old_price": old_price,
                "image_url": image_url,
                "image_urls": getattr(product, "image_urls", []),
                "short_description": getattr(product, "short_description", ""),
                "long_description": getattr(product, "long_description", ""),
                "in_stock": getattr(product, "in_stock", False),
                "stock": getattr(product, "stock", 0),
                "view_count": getattr(product, "view_count", 0),
                "rating_avg": getattr(product, "rating_avg", 0),
                "review_count": getattr(product, "review_count", 0),
                "sale_count": getattr(product, "sale_count", 0),
                "featured": getattr(product, "featured", False),
                "is_new": getattr(product, "is_new", False),
                "is_bestseller": getattr(product, "is_bestseller", False),
                "new": getattr(product, "is_new", False),  # Duplicate for template compatibility
                "bestseller": getattr(product, "is_bestseller", False),  # Duplicate for template compatibility
                "category": primary_category,
                "variants": formatted_variants,
                "has_variants": len(formatted_variants) > 0
            })

        return create_json_response(
            {
                "success": True,
                "bestseller_products": formatted_products
            },
            http_status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Error fetching bestseller products: {str(e)}")
        return create_json_response(
            {
                "success": False,
                "message": "An error occurred while fetching bestseller products"
            },
            http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@router.get("/featured-products")
@timed_cache(seconds=300)  # Cache results for 5 minutes
async def get_featured_products(
    limit: int = Query(8, ge=1, le=20)
):
    """API endpoint to fetch featured products for homepage"""
    try:
        # Get featured products
        featured_products = await Product.find({"status": "published", "featured": True}).limit(limit).to_list()

        # Format products for response
        formatted_products = []
        for product in featured_products:
            # Get base price
            base_price = product.get_base_price() if hasattr(product, "get_base_price") else 0

            # Get first image
            image_url = product.image_urls[0] if product.image_urls else ""

            # Format variants for display - only include the highest price variant
            formatted_variants = []
            highest_price_variant = None
            highest_price = 0

            if hasattr(product, "variants") and product.variants:
                for variant_type, variant_values in product.variants.items():
                    for variant in variant_values:
                        # Check if variant is a dict or object
                        variant_price = 0
                        variant_value = ""
                        variant_id = ""

                        if isinstance(variant, dict):
                            variant_price = variant.get("price", 0)
                            variant_value = variant.get("value", "")
                            variant_id = variant.get("id", str(uuid.uuid4()))
                        else:
                            variant_price = getattr(variant, "price", 0)
                            variant_value = getattr(variant, "value", "")
                            variant_id = getattr(variant, "id", str(uuid.uuid4()))

                        if variant_price > highest_price:
                            highest_price = variant_price
                            highest_price_variant = {
                                "id": variant_id,
                                "type": variant_type,
                                "value": variant_value,
                                "price": variant_price,
                                "display_name": f"{variant_value}"
                            }

            # Create a list with just the highest price variant, or empty if no variants
            formatted_variants = [highest_price_variant] if highest_price_variant else []

            # Calculate if there's a discounted price
            old_price = None
            current_price = base_price

            # Check if any variant has a discount
            if formatted_variants:
                for variant in formatted_variants:
                    if variant.get("discount_percentage") and variant.get("discount_percentage") > 0:
                        discount_percentage = variant.get("discount_percentage")
                        variant_price = variant.get("price")
                        if variant_price and discount_percentage:
                            old_price = variant_price
                            current_price = round(variant_price * (1 - (discount_percentage / 100)))
                            break

            # Get primary category if available
            primary_category = None
            if hasattr(product, "category_ids") and product.category_ids and len(product.category_ids) > 0:
                # Just use the first category ID as primary for now
                primary_category = product.category_ids[0]

            formatted_products.append({
                "id": product.id,
                "name": product.name,
                "price": current_price,
                "old_price": old_price,
                "image_url": image_url,
                "image_urls": getattr(product, "image_urls", []),
                "short_description": getattr(product, "short_description", ""),
                "long_description": getattr(product, "long_description", ""),
                "in_stock": getattr(product, "in_stock", False),
                "stock": getattr(product, "stock", 0),
                "view_count": getattr(product, "view_count", 0),
                "rating_avg": getattr(product, "rating_avg", 0),
                "review_count": getattr(product, "review_count", 0),
                "featured": getattr(product, "featured", False),
                "is_new": getattr(product, "is_new", False),
                "is_bestseller": getattr(product, "is_bestseller", False),
                "new": getattr(product, "is_new", False),  # Duplicate for template compatibility
                "bestseller": getattr(product, "is_bestseller", False),  # Duplicate for template compatibility
                "category": primary_category,
                "variants": formatted_variants,
                "has_variants": len(formatted_variants) > 0
            })

        return create_json_response(
            {
                "success": True,
                "featured_products": formatted_products
            },
            http_status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Error fetching featured products: {str(e)}")
        return create_json_response(
            {
                "success": False,
                "message": "An error occurred while fetching featured products"
            },
            http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )




@router.get("/products/{product_id}/related")
@timed_cache(seconds=60)  # Cache results for 60 seconds
async def get_related_products(
    product_id: str,
    limit: int = Query(4, ge=1, le=12)
):
    """API endpoint to fetch products related to a specific product"""
    try:
        # Try to find the source product
        product = await Product.find_one({"$or": [{"id": product_id}, {"_id": product_id}]})

        if not product:
            return create_json_response(
                {
                    "success": False,
                    "message": "Product not found"
                },
                http_status.HTTP_404_NOT_FOUND
            )

        # Get related products based on categories, brand, or tags
        query = {
            "status": "published",
            "$or": []
        }

        # Add category-based relation
        if hasattr(product, "category_ids") and product.category_ids:
            query["$or"].append({"category_ids": {"$in": product.category_ids}})

        # Add brand-based relation
        if hasattr(product, "brand_id") and product.brand_id:
            query["$or"].append({"brand_id": product.brand_id})

        # Add tag-based relation
        if hasattr(product, "tags") and product.tags:
            query["$or"].append({"tags": {"$in": product.tags}})

        # Exclude the current product
        query["id"] = {"$ne": product.id}

        # If no relation criteria, return newest products
        if not query["$or"]:
            related_products = await Product.find({"status": "published", "id": {"$ne": product.id}}).sort([("created_at", -1)]).limit(limit).to_list()
        else:
            related_products = await Product.find(query).limit(limit).to_list()

            # If not enough related products, add some newest products
            if len(related_products) < limit:
                needed = limit - len(related_products)
                existing_ids = [p.id for p in related_products] + [product.id]
                newest_products = await Product.find({"status": "published", "id": {"$nin": existing_ids}}).sort([("created_at", -1)]).limit(needed).to_list()
                related_products.extend(newest_products)

        # Format products for response
        formatted_products = []
        for related in related_products:
            # Get base price
            base_price = related.get_base_price() if hasattr(related, "get_base_price") else 0

            # Get first image
            image_url = related.image_urls[0] if related.image_urls else ""

            # Format variants for display - only include the highest price variant
            formatted_variants = []
            highest_price_variant = None
            highest_price = 0

            if hasattr(related, "variants") and related.variants:
                for variant_type, variant_values in related.variants.items():
                    for variant in variant_values:
                        # Check if variant is a dict or object
                        variant_price = 0
                        variant_value = ""
                        variant_id = ""

                        if isinstance(variant, dict):
                            variant_price = variant.get("price", 0)
                            variant_value = variant.get("value", "")
                            variant_id = variant.get("id", str(uuid.uuid4()))
                        else:
                            variant_price = getattr(variant, "price", 0)
                            variant_value = getattr(variant, "value", "")
                            variant_id = getattr(variant, "id", str(uuid.uuid4()))

                        if variant_price > highest_price:
                            highest_price = variant_price
                            highest_price_variant = {
                                "id": variant_id,
                                "type": variant_type,
                                "value": variant_value,
                                "price": variant_price,
                                "display_name": f"{variant_value}"
                            }

            # Create a list with just the highest price variant, or empty if no variants
            formatted_variants = [highest_price_variant] if highest_price_variant else []

            # Calculate if there's a discounted price
            old_price = None
            current_price = base_price

            # Check if any variant has a discount
            if formatted_variants:
                for variant in formatted_variants:
                    if variant.get("discount_percentage") and variant.get("discount_percentage") > 0:
                        discount_percentage = variant.get("discount_percentage")
                        variant_price = variant.get("price")
                        if variant_price and discount_percentage:
                            old_price = variant_price
                            current_price = round(variant_price * (1 - (discount_percentage / 100)))
                            break

            # Get primary category if available
            primary_category = None
            if hasattr(related, "category_ids") and related.category_ids and len(related.category_ids) > 0:
                # Just use the first category ID as primary for now
                primary_category = related.category_ids[0]

            formatted_products.append({
                "id": related.id,
                "name": related.name,
                "price": current_price,
                "old_price": old_price,
                "image_url": image_url,
                "image_urls": getattr(related, "image_urls", []),
                "short_description": getattr(related, "short_description", ""),
                "long_description": getattr(related, "long_description", ""),
                "in_stock": getattr(related, "in_stock", False),
                "stock": getattr(related, "stock", 0),
                "view_count": getattr(related, "view_count", 0),
                "rating_avg": getattr(related, "rating_avg", 0),
                "review_count": getattr(related, "review_count", 0),
                "featured": getattr(related, "featured", False),
                "is_new": getattr(related, "is_new", False),
                "is_bestseller": getattr(related, "is_bestseller", False),
                "new": getattr(related, "is_new", False),  # Duplicate for template compatibility
                "bestseller": getattr(related, "is_bestseller", False),  # Duplicate for template compatibility
                "category": primary_category,
                "variants": formatted_variants,
                "has_variants": len(formatted_variants) > 0
            })

        return create_json_response(
            {
                "success": True,
                "related_products": formatted_products
            },
            http_status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Error fetching related products for {product_id}: {str(e)}")
        return create_json_response(
            {
                "success": False,
                "message": "An error occurred while fetching related products"
            },
            http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@router.post("/contact")
async def submit_contact_form(
    subject: str = Body(...),
    message: str = Body(...),
    name: Optional[str] = Body(None),
    email: Optional[str] = Body(None),
    phone: Optional[str] = Body(None),
    user_id: Optional[str] = Body(None),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Submit a contact form message"""
    try:
        # Create user info object
        user_info = None

        # If user is logged in, use their information
        if current_user:
            user_info = MessageUser(
                name=current_user.username,
                email=current_user.email,
                phone=getattr(current_user, 'phone_number', None)
            )
            user_id = str(current_user.id)
        # Otherwise use the provided information
        elif name and email:
            user_info = MessageUser(
                name=name,
                email=email,
                phone=phone
            )
        else:
            return create_json_response(
                {
                    "success": False,
                    "message": "Name and email are required when not logged in"
                },
                http_status.HTTP_400_BAD_REQUEST
            )

        # Create and save the message
        user_message = Message(
            user_info=user_info,
            subject=subject,
            message=message,
            user_id=user_id
        )

        await user_message.save()

        return create_json_response(
            {
                "success": True,
                "message": "Your message has been sent successfully. We'll get back to you soon!"
            },
            http_status.HTTP_201_CREATED
        )
    except Exception as e:
        logger.error(f"Error submitting contact form: {str(e)}")
        return create_json_response(
            {
                "success": False,
                "message": "An error occurred while submitting your message. Please try again later."
            },
            http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )
