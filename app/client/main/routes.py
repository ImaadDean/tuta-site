from fastapi import Request, Depends, HTTPException
from app.client.main import router, templates
from fastapi.templating import Jinja2Templates
from app.models.product import Product
from app.models.banner import Banner
from app.models.collection import Collection
from app.models.category import Category
from app.database import get_db, initialize_mongodb
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import uuid
from fastapi.responses import RedirectResponse
import logging
from fastapi.responses import HTMLResponse
from typing import Optional, Dict, Any, List
from app.auth.jwt import get_current_user_optional, get_current_active_client
from app.models.user import User
import asyncio

logger = logging.getLogger(__name__)

# Error handling helper
async def safe_db_operation(operation, fallback_value=None, error_message="Database operation failed"):
    """Execute a database operation safely with error handling"""
    try:
        return await operation
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            logger.error(f"Event loop closed during database operation: {str(e)}")
            # Create a new event loop if the current one is closed
            try:
                # Try to re-initialize the database connection
                await initialize_mongodb()
                # Try the operation again with a fresh connection
                try:
                    return await operation
                except Exception as retry_error:
                    logger.error(f"Failed retry after event loop closed: {str(retry_error)}")
                    return fallback_value
            except Exception as conn_error:
                logger.error(f"Failed to re-initialize connection: {str(conn_error)}")
                return fallback_value
        raise
    except asyncio.CancelledError:
        logger.error("Database operation was cancelled (serverless timeout)")
        return fallback_value
    except Exception as e:
        logger.error(f"{error_message}: {str(e)}")
        # For other exceptions, also return the fallback
        return fallback_value

@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_active_client)
):
    """Home page with featured products, banners, categories, and collections"""
    try:
        # Fetch data with safe operations
        banners = await safe_db_operation(
            Banner.find({"is_active": True}).to_list(),
            fallback_value=[],
            error_message="Failed to fetch banners"
        )

        # Get featured products
        featured_products = await safe_db_operation(
            Product.find({"featured": True, "status": "published"}).limit(8).to_list(),
            fallback_value=[],
            error_message="Failed to fetch featured products"
        )

        # Get bestseller products using the dedicated method
        bestseller_products = await safe_db_operation(
            Product.get_bestsellers(limit=8),
            fallback_value=[],
            error_message="Failed to fetch bestseller products"
        )

        # Get new arrivals
        new_arrivals = await safe_db_operation(
            Product.find({"status": "published"}).sort([("created_at", -1)]).limit(4).to_list(),
            fallback_value=[],
            error_message="Failed to fetch new arrivals"
        )

        # Get trending products (most viewed in the last 30 days)
        trending_products = await safe_db_operation(
            Product.find({"status": "published"}).sort([("view_count", -1)]).limit(8).to_list(),
            fallback_value=[],
            error_message="Failed to fetch trending products"
        )

        # Get top rated products
        top_rated_products = await safe_db_operation(
            Product.find({"status": "published"}).sort([("rating_avg", -1)]).limit(8).to_list(),
            fallback_value=[],
            error_message="Failed to fetch top rated products"
        )

        # Get categories
        categories = await safe_db_operation(
            Category.find({"is_active": True}).to_list(length=None),
            fallback_value=[],
            error_message="Failed to fetch categories"
        )

        # Get collections
        collections = await safe_db_operation(
            Collection.find({"is_active": True}).to_list(length=None),
            fallback_value=[],
            error_message="Failed to fetch collections"
        )

        # Helper function to format product data with variants
        def format_product(product):
            # Ensure we have at least one image
            image_urls = product.image_urls if product.image_urls else ["/static/images/product-placeholder.jpg"]

            # Use the base_price property instead of calculating it
            base_price = product.base_price

            # Find the variant with the highest price
            highest_price_variant = None
            highest_price = 0

            if hasattr(product, 'variants') and product.variants:
                for variant_type, variant_values in product.variants.items():
                    for variant in variant_values:
                        variant_price = getattr(variant, 'price', 0) if not isinstance(variant, dict) else variant.get('price', 0)

                        if variant_price > highest_price:
                            highest_price = variant_price
                            variant_id = getattr(variant, 'id', str(uuid.uuid4())) if not isinstance(variant, dict) else variant.get('id', str(uuid.uuid4()))
                            variant_value = getattr(variant, 'value', '') if not isinstance(variant, dict) else variant.get('value', '')

                            highest_price_variant = {
                                'id': variant_id,
                                'type': variant_type,
                                'value': variant_value,
                                'price': variant_price,
                                'display_name': f"{variant_value}"
                            }

            # Create a list with just the highest price variant, or empty if no variants
            formatted_variants = [highest_price_variant] if highest_price_variant else []

            return {
                "id": product.id,
                "name": product.name,
                "price": base_price,
                "image_urls": image_urls,
                "view_count": getattr(product, 'view_count', 0),
                "rating_avg": getattr(product, 'rating_avg', 0),
                "review_count": getattr(product, 'review_count', 0),
                "sales_count": getattr(product, 'sales_count', 0),
                "bestseller": getattr(product, 'is_bestseller', False),
                "new": getattr(product, 'is_new', False),
                "stock": getattr(product, 'stock', 0),
                "short_description": getattr(product, 'short_description', ''),
                "long_description": getattr(product, 'long_description', ''),
                "variants": formatted_variants,  # Now contains only the highest price variant
                "has_variants": len(formatted_variants) > 0  # Flag to check if product has variants
            }
        # Get all published products for the "Our Products" section
        all_products = await safe_db_operation(
            Product.find({"status": "published"}).limit(12).to_list(),
            fallback_value=[],
            error_message="Failed to fetch all products"
        )

        # Format product lists
        formatted_featured = [format_product(p) for p in featured_products]
        formatted_bestsellers = [format_product(p) for p in bestseller_products]
        formatted_new_arrivals = [format_product(p) for p in new_arrivals]
        formatted_trending = [format_product(p) for p in trending_products]
        formatted_top_rated = [format_product(p) for p in top_rated_products]
        formatted_products = [format_product(p) for p in all_products]

        # Return the template with all the data
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "banners": banners,
                "featured_products": formatted_featured,
                "bestseller_products": formatted_bestsellers,
                "new_arrivals": formatted_new_arrivals,
                "trending_products": formatted_trending,
                "top_rated_products": formatted_top_rated,
                "products": formatted_products,
                "categories": categories,
                "collections": collections,
                "best_sellers_sidebar": formatted_bestsellers,
                "current_user": current_user
            }
        )
    except Exception as e:
        logger.error(f"Error rendering home page: {str(e)}")
        # In case of an error, return a basic template with minimal data
        return templates.TemplateResponse(
                "index.html",
            {
                "request": request,
                    "banners": [],
                    "featured_products": [],
                    "bestseller_products": [],
                    "new_arrivals": [],
                    "trending_products": [],
                    "top_rated_products": [],
                    "products": [],
                    "categories": [],
                    "collections": [],
                    "best_sellers_sidebar": [],
                    "error_message": "Failed to load some content. Please refresh the page.",
                    "current_user": current_user
                }
            )

@router.get("/about", response_class=HTMLResponse)
async def about_page(
    request: Request,
    current_user: Optional[User] = Depends(get_current_active_client)
):
    """About page with company information"""
    try:
        # Get categories and collections for sidebar
        categories = await safe_db_operation(
            Category.find({"is_active": True}).to_list(length=None),
            fallback_value=[],
            error_message="Failed to fetch categories"
        )

        # Get collections
        collections = await safe_db_operation(
            Collection.find({"is_active": True}).to_list(length=None),
            fallback_value=[],
            error_message="Failed to fetch collections"
        )

        # Get bestseller products for sidebar
        bestseller_products = await safe_db_operation(
            Product.get_bestsellers(limit=4),
            fallback_value=[],
            error_message="Failed to fetch bestseller products"
        )

        # Format bestseller products
        formatted_bestsellers = []
        for product in bestseller_products:
            # Ensure we have at least one image
            image_urls = product.image_urls if product.image_urls else ["/static/images/product-placeholder.jpg"]

            formatted_bestsellers.append({
                "id": product.id,
                "name": product.name,
                "price": product.base_price,
                "image_urls": image_urls,
                "rating_avg": getattr(product, 'rating_avg', 0),
                "stock": getattr(product, 'stock', 0),
                "variants": getattr(product, 'variants', [])
            })

        return templates.TemplateResponse(
            "about.html",
            {
                "request": request,
                "current_user": current_user,
                "categories": categories,
                "collections": collections,
                "best_sellers_sidebar": formatted_bestsellers
            }
        )
    except Exception as e:
        logger.error(f"Error rendering about page: {str(e)}")
        return templates.TemplateResponse(
            "about.html",
            {
                "request": request,
                "current_user": current_user,
                "categories": [],
                "collections": [],
                "best_sellers_sidebar": [],
                "error_message": "Failed to load some content. Please refresh the page."
            }
        )

@router.get("/contact", response_class=HTMLResponse)
async def contact_page(
    request: Request,
    current_user: Optional[User] = Depends(get_current_active_client)
):
    """Contact page with contact form and information"""
    try:
        # Get categories and collections for sidebar
        categories = await safe_db_operation(
            Category.find({"is_active": True}).to_list(length=None),
            fallback_value=[],
            error_message="Failed to fetch categories"
        )

        # Get collections
        collections = await safe_db_operation(
            Collection.find({"is_active": True}).to_list(length=None),
            fallback_value=[],
            error_message="Failed to fetch collections"
        )

        # Get bestseller products for sidebar
        bestseller_products = await safe_db_operation(
            Product.get_bestsellers(limit=4),
            fallback_value=[],
            error_message="Failed to fetch bestseller products"
        )

        # Get contact information from database
        from app.models.contact_info import ContactInfo
        contact_info = await safe_db_operation(
            ContactInfo.get_active(),
            fallback_value=None,
            error_message="Failed to fetch contact information"
        )

        # Format bestseller products
        formatted_bestsellers = []
        for product in bestseller_products:
            # Ensure we have at least one image
            image_urls = product.image_urls if product.image_urls else ["/static/images/product-placeholder.jpg"]

            formatted_bestsellers.append({
                "id": product.id,
                "name": product.name,
                "price": product.base_price,
                "image_urls": image_urls,
                "rating_avg": getattr(product, 'rating_avg', 0),
                "stock": getattr(product, 'stock', 0),
                "variants": getattr(product, 'variants', [])
            })

        return templates.TemplateResponse(
            "contact.html",
            {
                "request": request,
                "current_user": current_user,
                "categories": categories,
                "collections": collections,
                "best_sellers_sidebar": formatted_bestsellers,
                "contact_info": contact_info
            }
        )
    except Exception as e:
        logger.error(f"Error rendering contact page: {str(e)}")
        return templates.TemplateResponse(
            "contact.html",
            {
                "request": request,
                "current_user": current_user,
                "categories": [],
                "collections": [],
                "best_sellers_sidebar": [],
                "contact_info": None,
                "error_message": "Failed to load some content. Please refresh the page."
            }
        )