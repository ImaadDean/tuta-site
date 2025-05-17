from fastapi import APIRouter, Request, Depends, HTTPException, Body
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any, Union, Literal
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
import functools
import time

from app.models.user import User
from app.models.product import Product, DiscountActivity
from app.models.brand import Brand
from app.models.category import Category
from app.auth.jwt import get_current_active_admin
from app.database import get_db
from app.admin.products import router
from app.tasks import (
    update_bestseller_products, update_trending_products,
    update_top_rated_products, update_new_arrivals,
    get_task_status, get_all_tasks_status
)
import asyncio

# Helper function to serialize datetime objects for JSON responses
def serialize_datetime(obj: Any) -> Any:
    """
    Recursively convert datetime objects to ISO format strings for JSON serialization.

    Args:
        obj: The object to serialize

    Returns:
        The serialized object with datetime objects converted to strings
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: serialize_datetime(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_datetime(item) for item in obj]
    return obj

# Configure logging
logger = logging.getLogger(__name__)

# Simple in-memory cache
_CACHE = {}

def clear_product_cache():
    """Clear all product-related cache entries"""
    keys_to_remove = []
    for key in _CACHE.keys():
        if key.startswith("get_dashboard_products") or key.startswith("get_product_variants"):
            keys_to_remove.append(key)

    for key in keys_to_remove:
        _CACHE.pop(key, None)

    logger.debug(f"Cleared {len(keys_to_remove)} product cache entries")

def timed_cache(seconds=60):
    """
    Simple time-based cache decorator

    Args:
        seconds: Number of seconds to cache the result

    Returns:
        Decorated function with caching
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Create a cache key from the function name and arguments
            key_parts = [func.__name__]
            # Add positional args to key
            key_parts.extend([str(arg) for arg in args if not isinstance(arg, Request)])
            # Add keyword args to key (sorted to ensure consistent order)
            key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())
                             if k not in ('current_user', 'db', 'request')])
            cache_key = ":".join(key_parts)

            # Check if we have a valid cached result
            if cache_key in _CACHE:
                result, timestamp = _CACHE[cache_key]
                if time.time() - timestamp < seconds:
                    logger.debug(f"Cache hit for {cache_key}")
                    return result

            # No valid cache, call the function
            logger.debug(f"Cache miss for {cache_key}")
            result = await func(*args, **kwargs)

            # Cache the result
            _CACHE[cache_key] = (result, time.time())

            return result
        return wrapper
    return decorator


# Product listing endpoint
@router.get("/api/get-products", response_class=JSONResponse)
@timed_cache(seconds=30)  # Cache results for 30 seconds
async def get_dashboard_products(
    request: Request,
    status: Optional[str] = None,
    category_id: Optional[str] = None,
    brand_id: Optional[str] = None,
    search: Optional[str] = None,
    featured: Optional[bool] = None,
    is_new: Optional[bool] = None,
    is_bestseller: Optional[bool] = None,
    limit: int = 8,
    skip: int = 0,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """API endpoint to fetch products for dashboard with filtering and search"""
    try:
        # Build the query filter
        query_filter = {}

        # Add status filter if provided
        if status:
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

        # Add new product filter if provided
        if is_new is not None:
            query_filter["is_new"] = is_new

        # Add bestseller filter if provided
        if is_bestseller is not None:
            query_filter["is_bestseller"] = is_bestseller

        # Add search filter if provided
        if search:
            # Search in name and description
            query_filter["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"short_description": {"$regex": search, "$options": "i"}},
                {"long_description": {"$regex": search, "$options": "i"}}
            ]

        # Get total count for pagination - use projection to make it faster
        total_count = await Product.find(query_filter, projection={"_id": 1}).count()

        # Determine the best index to use based on the query
        index_hint = None
        if status:
            index_hint = "status_1"
        elif brand_id:
            index_hint = "brand_id_1"
        elif category_id:
            index_hint = "category_ids_1"
        elif featured is not None:
            index_hint = "featured_1"
        elif is_new is not None:
            index_hint = "is_new_1"
        elif is_bestseller is not None:
            index_hint = "is_bestseller_1"

        # Prepare the aggregation pipeline
        pipeline = [
            # Match products based on the query filter
            {"$match": query_filter},
            # Skip and limit for pagination
            {"$skip": skip},
            {"$limit": limit},
            # Project only the fields we need
            {"$project": {
                "_id": 1,
                "id": 1,
                "name": 1,
                "short_description": 1,
                "image_urls": 1,
                "stock": 1,
                "in_stock": 1,
                "status": 1,
                "featured": 1,
                "is_new": 1,
                "is_bestseller": 1,
                "brand_id": 1,
                "category_ids": 1,
                "variants": 1,
                "created_at": 1,
                "updated_at": 1
            }}
        ]

        # Add index hint if we have one
        if index_hint:
            pipeline.append({"$hint": index_hint})

        # Execute the aggregation pipeline
        products_cursor = Product.aggregate(pipeline)
        products = await products_cursor.to_list(length=limit)

        # Fetch all brand and category data in bulk to avoid N+1 queries
        all_brand_ids = [p["brand_id"] for p in products if "brand_id" in p and p["brand_id"]]
        all_category_ids = []
        for p in products:
            if "category_ids" in p and p["category_ids"]:
                all_category_ids.extend(p["category_ids"])

        # Remove duplicates
        all_brand_ids = list(set(all_brand_ids))
        all_category_ids = list(set(all_category_ids))

        # Fetch all brands and categories in bulk
        brands = {}
        categories = {}

        if all_brand_ids:
            brand_docs = await Brand.find({"id": {"$in": all_brand_ids}}).to_list()
            brands = {brand.id: brand.name for brand in brand_docs}

        if all_category_ids:
            category_docs = await Category.find({"id": {"$in": all_category_ids}}).to_list()
            categories = {cat.id: {"id": cat.id, "name": cat.name} for cat in category_docs}

        # Process products for response
        processed_products = []
        for product in products:
            # Get brand name if available
            brand_name = None
            if "brand_id" in product and product["brand_id"] in brands:
                brand_name = brands[product["brand_id"]]

            # Get categories if available
            product_categories = []
            if "category_ids" in product and product["category_ids"]:
                for cat_id in product["category_ids"]:
                    if cat_id in categories:
                        product_categories.append(categories[cat_id])

            # Calculate price information efficiently
            lowest_price = float('inf')
            highest_price = 0

            if "variants" in product and product["variants"]:
                for variant_type, variant_values in product["variants"].items():
                    for variant in variant_values:
                        price = 0
                        if isinstance(variant, dict) and "price" in variant:
                            price = variant["price"]
                        elif hasattr(variant, "price"):
                            price = variant.price

                        if price > 0:
                            lowest_price = min(lowest_price, price)
                            highest_price = max(highest_price, price)

            if lowest_price == float('inf'):
                lowest_price = 0

            # Format price with commas
            formatted_lowest_price = f"UGX {lowest_price:,}" if lowest_price else "N/A"
            formatted_highest_price = f"UGX {highest_price:,}" if highest_price else "N/A"

            # Create a price range string
            price_range = formatted_lowest_price
            if lowest_price != highest_price:
                price_range = f"{formatted_lowest_price} - {formatted_highest_price}"

            # Create processed product object
            processed_product = {
                "id": product["_id"],
                "name": product["name"],
                "short_description": product.get("short_description"),
                "image_url": product["image_urls"][0] if "image_urls" in product and product["image_urls"] else None,
                "price_range": price_range,
                "stock": product.get("stock", 0),
                "in_stock": product.get("in_stock", False),
                "status": product.get("status", "published"),
                "featured": product.get("featured", False),
                "is_new": product.get("is_new", False),
                "is_bestseller": product.get("is_bestseller", False),
                "brand_name": brand_name,
                "categories": product_categories,
                "created_at": product["created_at"].isoformat() if "created_at" in product and product["created_at"] else None,
                "updated_at": product["updated_at"].isoformat() if "updated_at" in product and product["updated_at"] else None
            }

            processed_products.append(processed_product)

        # Calculate pagination information
        current_page = skip // limit + 1 if limit > 0 else 1
        total_pages = (total_count + limit - 1) // limit if limit > 0 else 1

        # Return the response
        return JSONResponse(content={
            "success": True,
            "products": processed_products,
            "total": total_count,
            "has_more": total_count > (skip + limit),
            "pagination": {
                "current_page": current_page,
                "total_pages": total_pages,
                "limit": limit,
                "skip": skip,
                "items_showing": f"{skip + 1}-{min(skip + limit, total_count)} of {total_count}"
            }
        })
    except Exception as e:
        logger.error(f"Error fetching dashboard products: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": f"Failed to fetch products: {str(e)}"}
        )


# Product variants endpoint
@router.get("/api/product/{product_id}/variants", response_class=JSONResponse)
@timed_cache(seconds=30)  # Cache results for 30 seconds
async def get_product_variants(
    request: Request,
    product_id: str,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """API endpoint to fetch variants for a specific product"""
    try:
        # Get the product
        product = await Product.find_one({"_id": product_id})
        if not product:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Product not found"}
            )

        # Extract variants
        variants_data = {}
        for variant_type, variant_values in product.variants.items():
            variants_data[variant_type] = []
            for variant in variant_values:
                # Check if variant is already a dict or needs conversion
                try:
                    if isinstance(variant, dict):
                        variant_dict = dict(variant)  # Make a copy to avoid modifying the original
                    elif hasattr(variant, 'model_dump'):
                        variant_dict = variant.model_dump()
                    elif hasattr(variant, 'dict'):
                        variant_dict = variant.dict()
                    else:
                        # Fallback to manual dict conversion
                        variant_dict = {}
                        for k, v in variant.__dict__.items():
                            if not k.startswith('_'):
                                variant_dict[k] = v
                except Exception as e:
                    logger.error(f"Error converting variant to dict: {str(e)}")
                    # Create a basic dict with essential properties
                    variant_dict = {
                        "id": getattr(variant, 'id', None),
                        "value": getattr(variant, 'value', None),
                        "price": getattr(variant, 'price', 0)
                    }

                # Add current discount status
                now = datetime.now()
                is_on_discount = False

                # Convert datetime objects to ISO strings for JSON serialization
                if 'discount_start_date' in variant_dict and isinstance(variant_dict['discount_start_date'], datetime):
                    variant_dict['discount_start_date'] = variant_dict['discount_start_date'].isoformat()

                if 'discount_end_date' in variant_dict and isinstance(variant_dict['discount_end_date'], datetime):
                    variant_dict['discount_end_date'] = variant_dict['discount_end_date'].isoformat()

                if variant_dict.get('discount_percentage') and variant_dict.get('discount_percentage') > 0:
                    # Check if discount is active based on dates
                    start_date = variant_dict.get('discount_start_date')
                    end_date = variant_dict.get('discount_end_date')

                    # Convert string dates to datetime for comparison
                    if isinstance(start_date, str):
                        try:
                            start_date_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                        except:
                            start_date_dt = None
                    else:
                        start_date_dt = start_date

                    if isinstance(end_date, str):
                        try:
                            end_date_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                        except:
                            end_date_dt = None
                    else:
                        end_date_dt = end_date

                    # Check if discount is currently active
                    if (not start_date_dt or now >= start_date_dt) and (not end_date_dt or now <= end_date_dt):
                        is_on_discount = True

                variant_dict['is_on_discount'] = is_on_discount
                variants_data[variant_type].append(variant_dict)

        # Create a JSON-serializable response
        response_data = {
            "success": True,
            "product_id": product_id,
            "product_name": product.name,
            "variants": variants_data,
            "last_restocked": product.last_restocked,
            "stock": product.stock,
            "in_stock": product.in_stock
        }

        # Apply serialization to the entire response
        serialized_response = serialize_datetime(response_data)

        return JSONResponse(content=serialized_response)
    except Exception as e:
        logger.error(f"Error fetching product variants: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": f"Failed to fetch product variants: {str(e)}"}
        )


# Set product discount endpoint
@router.post("/api/product/{product_id}/set-discount", response_class=JSONResponse)
async def set_product_variant_discount(
    request: Request,
    product_id: str,
    discount_data: Dict = Body(...),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """API endpoint to set a discount on a product variant"""
    try:
        # Get the product
        product = await Product.find_one({"_id": product_id})
        if not product:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Product not found"}
            )

        # Extract discount data
        variant_type = discount_data.get("variant_type")
        variant_id = discount_data.get("variant_id")
        discount_percentage = float(discount_data.get("discount_percentage", 0))

        # Get quantity limit (number of items that can be sold at discount)
        quantity_limit = int(discount_data.get("quantity_limit", 0))

        # Parse dates
        start_date_str = discount_data.get("start_date")
        end_date_str = discount_data.get("end_date")

        start_date = None
        end_date = None

        if start_date_str:
            try:
                start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "detail": "Invalid start date format"}
                )

        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "detail": "Invalid end date format"}
                )

        # Validate discount percentage
        if discount_percentage <= 0 or discount_percentage > 100:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Discount percentage must be between 0 and 100"}
            )

        # Validate dates
        if start_date and end_date and start_date >= end_date:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": "Start date must be before end date"}
            )

        # Find the variant and update its discount
        variant_found = False
        if variant_type in product.variants:
            for i, variant in enumerate(product.variants[variant_type]):
                # Get the variant ID, checking different possible locations
                try:
                    if hasattr(variant, 'id'):
                        variant_id_to_check = variant.id
                    elif isinstance(variant, dict) and 'id' in variant:
                        variant_id_to_check = variant['id']
                    else:
                        # If we can't find an ID, skip this variant
                        logger.warning(f"Variant without ID found in product {product_id}, skipping")
                        continue
                except Exception as e:
                    logger.warning(f"Error getting variant ID: {str(e)}, skipping")
                    continue

                if variant_id_to_check == variant_id:
                    # Create a discount activity record
                    discount_activity = DiscountActivity(
                        discount_percentage=discount_percentage,
                        start_date=start_date or datetime.now(),
                        end_date=end_date or (datetime.now() + timedelta(days=365)),  # Default to 1 year if not specified
                        quantity_limit=quantity_limit if quantity_limit > 0 else None,
                        is_active=True
                    )

                    # Update the variant with discount information
                    if hasattr(variant, 'discount_percentage'):
                        variant.discount_percentage = discount_percentage
                        variant.discount_start_date = start_date or datetime.now()
                        variant.discount_end_date = end_date or (datetime.now() + timedelta(days=365))
                        variant.discount_quantity_limit = quantity_limit if quantity_limit > 0 else None
                        variant.discount_quantity_used = 0

                        # Add to discount activity history
                        if not hasattr(variant, 'discount_activity'):
                            variant.discount_activity = []
                        variant.discount_activity.append(discount_activity)
                    else:
                        # Handle dictionary variant
                        variant['discount_percentage'] = discount_percentage
                        variant['discount_start_date'] = start_date or datetime.now()
                        variant['discount_end_date'] = end_date or (datetime.now() + timedelta(days=365))
                        variant['discount_quantity_limit'] = quantity_limit if quantity_limit > 0 else None
                        variant['discount_quantity_used'] = 0

                        # Add to discount activity history
                        if 'discount_activity' not in variant:
                            variant['discount_activity'] = []
                        variant['discount_activity'].append(discount_activity.model_dump())

                    variant_found = True
                    break

        if not variant_found:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Variant not found"}
            )

        # Save the updated product
        await product.save()

        # Clear the product cache to ensure fresh data is returned
        clear_product_cache()

        # Prepare response data
        response_data = {
            "success": True,
            "message": "Discount set successfully",
            "product_id": product_id,
            "variant_id": variant_id,
            "discount_percentage": discount_percentage,
            "start_date": start_date,  # Let serialize_datetime handle the conversion
            "end_date": end_date,      # Let serialize_datetime handle the conversion
            "quantity_limit": quantity_limit
        }

        # Apply serialization to ensure no datetime objects
        serialized_response = serialize_datetime(response_data)

        return JSONResponse(content=serialized_response)
    except Exception as e:
        logger.error(f"Error setting product variant discount: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": f"Failed to set discount: {str(e)}"}
        )


# Remove product discount endpoint
@router.post("/api/product/{product_id}/remove-discount", response_class=JSONResponse)
async def remove_product_variant_discount(
    request: Request,
    product_id: str,
    variant_data: Dict = Body(...),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """API endpoint to remove a discount from a product variant"""
    try:
        # Get the product
        product = await Product.find_one({"_id": product_id})
        if not product:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Product not found"}
            )

        # Extract variant data
        variant_type = variant_data.get("variant_type")
        variant_id = variant_data.get("variant_id")

        # Find the variant and remove its discount
        variant_found = False
        if variant_type in product.variants:
            for i, variant in enumerate(product.variants[variant_type]):
                # Get the variant ID, checking different possible locations
                try:
                    if hasattr(variant, 'id'):
                        variant_id_to_check = variant.id
                    elif isinstance(variant, dict) and 'id' in variant:
                        variant_id_to_check = variant['id']
                    else:
                        # If we can't find an ID, skip this variant
                        logger.warning(f"Variant without ID found in product {product_id}, skipping")
                        continue
                except Exception as e:
                    logger.warning(f"Error getting variant ID: {str(e)}, skipping")
                    continue

                if variant_id_to_check == variant_id:
                    # Update the variant to remove discount information
                    if hasattr(variant, 'discount_percentage'):
                        variant.discount_percentage = None
                        variant.discount_start_date = None
                        variant.discount_end_date = None
                        variant.discount_quantity_limit = None
                        variant.discount_quantity_used = None

                        # Mark all discount activities as inactive
                        if hasattr(variant, 'discount_activity'):
                            for activity in variant.discount_activity:
                                activity.is_active = False
                    else:
                        # Handle dictionary variant
                        variant['discount_percentage'] = None
                        variant['discount_start_date'] = None
                        variant['discount_end_date'] = None
                        variant['discount_quantity_limit'] = None
                        variant['discount_quantity_used'] = None

                        # Mark all discount activities as inactive
                        if 'discount_activity' in variant:
                            for activity in variant['discount_activity']:
                                activity['is_active'] = False

                    variant_found = True
                    break

        if not variant_found:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Variant not found"}
            )

        # Save the updated product
        await product.save()

        # Clear the product cache to ensure fresh data is returned
        clear_product_cache()

        # Create a JSON-serializable response
        response_data = {
            "success": True,
            "message": "Discount removed successfully",
            "product_id": product_id,
            "variant_id": variant_id
        }

        # Apply serialization to ensure no datetime objects
        serialized_response = serialize_datetime(response_data)

        return JSONResponse(content=serialized_response)
    except Exception as e:
        logger.error(f"Error removing product variant discount: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": f"Failed to remove discount: {str(e)}"}
        )


# Manage product stock endpoint
@router.post("/api/product/{product_id}/manage-stock", response_class=JSONResponse)
async def manage_product_stock(
    request: Request,
    product_id: str,
    stock_data: Dict = Body(...),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """API endpoint to manage product stock (mark as out of stock, reduce stock, or restock)"""
    try:
        # Get the product
        product = await Product.find_one({"_id": product_id})
        if not product:
            return JSONResponse(
                status_code=404,
                content={"success": False, "detail": "Product not found"}
            )

        # Extract stock management data
        action = stock_data.get("action")
        quantity = stock_data.get("quantity", 0)

        # Validate action
        valid_actions = ["mark_out_of_stock", "reduce_stock", "restock"]
        if action not in valid_actions:
            return JSONResponse(
                status_code=400,
                content={"success": False, "detail": f"Invalid action. Must be one of: {', '.join(valid_actions)}"}
            )

        # Validate quantity for actions that require it
        if action in ["reduce_stock", "restock"]:
            try:
                quantity = int(quantity)
                if quantity <= 0:
                    return JSONResponse(
                        status_code=400,
                        content={"success": False, "detail": "Quantity must be a positive number"}
                    )
            except (ValueError, TypeError):
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "detail": "Quantity must be a valid number"}
                )

        # Perform the requested action
        if action == "mark_out_of_stock":
            # Set stock to 0 and mark as out of stock
            product.stock = 0
            product.in_stock = False
            message = "Product marked as out of stock"

        elif action == "reduce_stock":
            # Validate current stock
            if product.stock < quantity:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "detail": f"Cannot reduce stock by {quantity}. Current stock is {product.stock}"}
                )

            # Reduce stock by the specified quantity
            product.stock -= quantity

            # Update in_stock status if stock becomes 0
            if product.stock == 0:
                product.in_stock = False

            message = f"Stock reduced by {quantity}"

        elif action == "restock":
            # Increase stock by the specified quantity
            product.stock += quantity

            # Update total lifetime stock
            product.total_stock_lifetime += quantity

            # Update last restocked timestamp
            product.last_restocked = datetime.now()

            # Ensure in_stock is True if we have stock
            if product.stock > 0:
                product.in_stock = True

            message = f"Stock increased by {quantity}"

        # Save the updated product
        await product.save()

        # Clear the product cache to ensure fresh data is returned
        clear_product_cache()

        # Prepare response data
        response_data = {
            "success": True,
            "message": message,
            "product_id": product_id,
            "current_stock": product.stock,
            "in_stock": product.in_stock,
            "last_restocked": product.last_restocked
        }

        # Apply serialization to ensure no datetime objects
        serialized_response = serialize_datetime(response_data)

        return JSONResponse(content=serialized_response)
    except Exception as e:
        logger.error(f"Error managing product stock: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": f"Failed to manage product stock: {str(e)}"}
        )


# Product status management endpoints
@router.post("/api/update-bestsellers", response_class=JSONResponse)
async def trigger_bestseller_update(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """API endpoint to manually trigger the bestseller update task"""
    try:
        # Create a task to run the bestseller update
        task = asyncio.create_task(update_bestseller_products())

        return JSONResponse(content={
            "success": True,
            "message": "Bestseller update task started. This may take a few moments to complete."
        })
    except Exception as e:
        logger.error(f"Error triggering bestseller update: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": f"Failed to trigger bestseller update: {str(e)}"}
        )


@router.post("/api/update-trending", response_class=JSONResponse)
async def trigger_trending_update(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """API endpoint to manually trigger the trending products update task"""
    try:
        # Create a task to run the trending update
        task = asyncio.create_task(update_trending_products())

        return JSONResponse(content={
            "success": True,
            "message": "Trending products update task started. This may take a few moments to complete."
        })
    except Exception as e:
        logger.error(f"Error triggering trending products update: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": f"Failed to trigger trending products update: {str(e)}"}
        )


@router.post("/api/update-top-rated", response_class=JSONResponse)
async def trigger_top_rated_update(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """API endpoint to manually trigger the top rated products update task"""
    try:
        # Create a task to run the top rated update
        task = asyncio.create_task(update_top_rated_products())

        return JSONResponse(content={
            "success": True,
            "message": "Top rated products update task started. This may take a few moments to complete."
        })
    except Exception as e:
        logger.error(f"Error triggering top rated products update: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": f"Failed to trigger top rated products update: {str(e)}"}
        )


@router.post("/api/update-new-arrivals", response_class=JSONResponse)
async def trigger_new_arrivals_update(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """API endpoint to manually trigger the new arrivals update task"""
    try:
        # Create a task to run the new arrivals update
        task = asyncio.create_task(update_new_arrivals())

        return JSONResponse(content={
            "success": True,
            "message": "New arrivals update task started. This may take a few moments to complete."
        })
    except Exception as e:
        logger.error(f"Error triggering new arrivals update: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": f"Failed to trigger new arrivals update: {str(e)}"}
        )


@router.get("/api/background-tasks/status", response_class=JSONResponse)
async def get_background_tasks_status(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """API endpoint to get the status of all background tasks"""
    try:
        tasks_status = get_all_tasks_status()

        return JSONResponse(content={
            "success": True,
            "tasks": tasks_status
        })
    except Exception as e:
        logger.error(f"Error getting background tasks status: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": f"Failed to get background tasks status: {str(e)}"}
        )


@router.get("/api/product-counts", response_class=JSONResponse)
async def get_product_counts():
    """API endpoint to get counts of products by special status (bestseller, trending, top rated, new arrivals)"""
    try:
        # Get product counts
        counts = await Product.get_product_counts()

        return JSONResponse(content={
            "success": True,
            "counts": counts
        })
    except Exception as e:
        logger.error(f"Error getting product counts: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": f"Failed to get product counts: {str(e)}"}
        )
