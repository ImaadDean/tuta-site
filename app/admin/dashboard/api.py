from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from app.models.user import User
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.auth.jwt import get_current_active_admin
from app.database import get_db
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
from typing import Any
import logging
import functools
import time

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

# Import the router from the dashboard package
from app.admin.dashboard import router

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

@router.get("/api/dashboard/stats", response_class=JSONResponse)
async def get_dashboard_stats(
    request: Request,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """API endpoint to fetch dashboard statistics"""
    try:
        # Get pending orders count
        pending_orders = await Order.find(
            {"status": {"$in": [OrderStatus.PENDING.value, OrderStatus.PROCESSING.value, OrderStatus.DELIVERING.value]}}
        ).count()

        # Get today's sales
        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())

        daily_sales_pipeline = [
            {
                "$match": {
                    "created_at": {"$gte": today_start, "$lte": today_end},
                    "status": {"$ne": OrderStatus.CANCELLED.value}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": "$total_amount"}
                }
            }
        ]

        daily_sales = 0
        daily_sales_result = await Order.aggregate(daily_sales_pipeline).to_list()
        if daily_sales_result and len(daily_sales_result) > 0 and "total" in daily_sales_result[0]:
            daily_sales = daily_sales_result[0]["total"]

        # Format daily sales with commas and no decimal places
        formatted_daily_sales = f"UGX {int(daily_sales):,}"

        # Get total users count
        total_users = await User.find_all().count()

        # Get total products count
        total_products = await Product.find_all().count()

        return JSONResponse(content={
            "pending_orders": pending_orders,
            "daily_sales": formatted_daily_sales,
            "total_users": total_users,
            "total_products": total_products
        })
    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"Failed to fetch dashboard stats: {str(e)}"}
        )

# Note: Product-related API endpoints have been moved to app\admin\products\api.py

