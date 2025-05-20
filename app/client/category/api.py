from fastapi import APIRouter, Query, HTTPException, status, Request
from typing import Optional, List, Dict, Any, Union
from app.models.category import Category
from app.models.product import Product
from app.models.collection import Collection
from app.models.banner import Banner
from app.models.brand import Brand
from app.client.category import router
from app.utils.response import create_json_response
from app.utils.cache import timed_cache
import logging
from time import time
from contextlib import contextmanager

# Configure logger
logger = logging.getLogger(__name__)

@contextmanager
def log_api_execution_time(endpoint: str, request: Optional[Request] = None):
    """Context manager to log API execution time"""
    start_time = time()
    try:
        yield
    finally:
        execution_time = time() - start_time
        client_ip = request.client.host if request and hasattr(request, 'client') else 'unknown'
        logger.debug(f"API {endpoint} from {client_ip} completed in {execution_time:.2f}s")

@router.get("/api/categories")
@timed_cache(seconds=600)  # Cache results for 10 minutes
async def get_all_categories(
    request: Request,
    active_only: bool = Query(True, description="Only return active categories"),
    with_collection: bool = Query(False, description="Include collection data for each category"),
    limit: Optional[int] = Query(None, description="Maximum number of categories to return")
):
    """API endpoint to fetch all categories

    Args:
        request: The FastAPI request object
        active_only: Only return active categories
        with_collection: Include collection data for each category
        limit: Maximum number of categories to return

    Returns:
        JSON response with categories data
    """
    with log_api_execution_time("get_all_categories", request):
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
                    "id": str(category.id),
                    "name": category.name,
                    "description": category.description,
                    "icon_url": category.icon_url,
                    "product_count": category.product_count,
                    "is_active": category.is_active,
                    "collection_id": category.collection_id
                }

                # Include collection data if requested
                if with_collection and category.collection_id:
                    collection = await Collection.find_one({"_id": category.collection_id})
                    if collection:
                        category_data["collection"] = {
                            "id": str(collection.id),
                            "name": collection.name,
                            "image_url": collection.image_url
                        }

                formatted_categories.append(category_data)

            return create_json_response(
                {
                    "success": True,
                    "categories": formatted_categories,
                    "total": len(formatted_categories)
                },
                status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error fetching categories: {str(e)}", exc_info=True)
            return create_json_response(
                {
                    "success": False,
                    "message": "An error occurred while fetching categories",
                    "error": str(e) if logger.level <= logging.DEBUG else None
                },
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )

@router.get("/api/categories/{category_id}")
@timed_cache(seconds=600)  # Cache results for 10 minutes
async def get_category_by_id(
    request: Request,
    category_id: str,
    with_collection: bool = Query(False, description="Include collection data for the category"),
    with_products: bool = Query(False, description="Include products in this category"),
    products_limit: int = Query(10, description="Maximum number of products to return if with_products is True")
):
    """API endpoint to fetch a specific category by ID

    Args:
        request: The FastAPI request object
        category_id: ID of the category to get
        with_collection: Include collection data for the category
        with_products: Include products in this category
        products_limit: Maximum number of products to return if with_products is True

    Returns:
        JSON response with category data
    """
    with log_api_execution_time(f"get_category_by_id({category_id})", request):
        try:
            # Get the category - try both id and _id fields
            category = await Category.find_one({"id": category_id})
            if not category:
                # Try with _id as fallback
                category = await Category.find_one({"_id": category_id})

            if not category:
                return create_json_response(
                    {
                        "success": False,
                        "message": f"Category with ID {category_id} not found"
                    },
                    status.HTTP_404_NOT_FOUND
                )

            # Log for debugging
            logger.info(f"API: Found category: {category.name} (id: {category.id})")

            # Format category for response - use id in response
            category_data = {
                "id": str(category.id),  # Use the custom id field
                "name": category.name,
                "description": category.description,
                "icon_url": category.icon_url,
                "product_count": category.product_count,
                "is_active": category.is_active,
                "collection_id": category.collection_id
            }

            # Include collection data if requested
            if with_collection and category.collection_id:
                # Use id (not _id) in query since collection_id stores the custom id field
                collection = await Collection.find_one({"id": category.collection_id})
                if collection:
                    # Use id in response
                    category_data["collection"] = {
                        "id": str(collection.id),  # Use the custom id field
                        "name": collection.name,
                        "image_url": collection.image_url
                    }

            # Include products in this category if requested
            if with_products:
                # Use id (not _id) in query since category_ids stores the custom id field
                products = await Product.find(
                    {"category_ids": category.id, "status": "published", "in_stock": True}
                ).sort("created_at", -1).limit(products_limit).to_list()

                # Debug log to help troubleshoot
                print(f"Found {len(products)} products for category {category.id} ({category.name})")

                formatted_products = []
                for product in products:
                    # Get brand name if available
                    brand_name = None
                    if product.brand_id:
                        # Use id (not _id) in query since brand_id stores the custom id field
                        brand = await Brand.find_one({"id": product.brand_id})
                        if brand:
                            brand_name = brand.name

                    # Use id in response
                    formatted_products.append({
                        "id": str(product.id),  # Use the custom id field
                        "name": product.name,
                        "short_description": product.short_description,
                        "price": product.get_base_price() if hasattr(product, "get_base_price") else 0,
                        "discount_price": getattr(product, "discount_price", None),
                        "image_url": product.image_urls[0] if product.image_urls else None,
                        "rating_avg": product.rating_avg,
                        "review_count": product.review_count,
                        "in_stock": product.in_stock,
                        "is_new": product.is_new,
                        "is_bestseller": product.is_bestseller,
                        "is_trending": product.is_trending,
                        "is_top_rated": product.is_top_rated,
                        "brand_name": brand_name
                    })

                category_data["products"] = formatted_products

            # Get banner if available
            if category.banner_id:
                # Use _id in query
                banner = await Banner.find_one({"_id": category.banner_id})
                if banner:
                    # Use id in response
                    category_data["banner"] = {
                        "id": str(banner._id),
                        "title": banner.title,
                        "subtitle": banner.subtitle,
                        "image_url": banner.image_url,
                        "link": banner.link
                    }

            return create_json_response(
                {
                    "success": True,
                    "category": category_data
                },
                status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error fetching category {category_id}: {str(e)}", exc_info=True)
            return create_json_response(
                {
                    "success": False,
                    "message": "An error occurred while fetching the category",
                    "error": str(e) if logger.level <= logging.DEBUG else None
                },
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )

@router.get("/api/collections/{collection_id}/categories")
@timed_cache(seconds=600)  # Cache results for 10 minutes
async def get_collection_categories(
    request: Request,
    collection_id: str
):
    """API endpoint to fetch categories for a specific collection

    Args:
        request: The FastAPI request object
        collection_id: ID of the collection to get categories for

    Returns:
        JSON response with collection categories data
    """
    with log_api_execution_time(f"get_collection_categories({collection_id})", request):
        try:
            # Get the collection - use _id in query
            collection = await Collection.find_one({"_id": collection_id})
            if not collection:
                return create_json_response(
                    {
                        "success": False,
                        "message": f"Collection with ID {collection_id} not found"
                    },
                    status.HTTP_404_NOT_FOUND
                )

            # Get categories for this collection - use _id in query
            categories = await Category.find({"collection_id": collection._id, "is_active": True}).to_list()

            # Format categories for response - use id in response
            formatted_categories = []
            for category in categories:
                formatted_categories.append({
                    "id": str(category._id),
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
                status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error fetching categories for collection {collection_id}: {str(e)}", exc_info=True)
            return create_json_response(
                {
                    "success": False,
                    "message": "An error occurred while fetching categories",
                    "error": str(e) if logger.level <= logging.DEBUG else None
                },
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )

@router.get("/api/categories/{category_id}/detail")
@timed_cache(seconds=300)  # Cache results for 5 minutes
async def get_category_detail_api(
    request: Request,
    category_id: str,
    include_products: bool = Query(True, description="Include products in the response"),
    products_limit: int = Query(12, description="Number of products to include"),
    products_offset: int = Query(0, description="Offset for products pagination"),
    include_banner: bool = Query(True, description="Include banner in the response"),
    sort_by: str = Query("created_at", description="Sort products by field (created_at, price, rating_avg, sale_count)"),
    sort_order: str = Query("desc", description="Sort order (asc, desc)")
):
    """
    API endpoint to get category details for the category detail page

    Args:
        request: The FastAPI request object
        category_id: ID of the category to fetch
        include_products: Whether to include products in the response
        products_limit: Number of products to include if include_products is True
        products_offset: Offset for products pagination
        include_banner: Whether to include the category banner in the response
        sort_by: Field to sort products by
        sort_order: Sort order (asc or desc)

    Returns:
        JSON response with category details
    """
    with log_api_execution_time(f"get_category_detail_api({category_id})", request):
        try:
            # Get the category - try both id and _id fields
            category = await Category.find_one({"id": category_id})
            if not category:
                # Try with _id as fallback
                category = await Category.find_one({"_id": category_id})

            if not category:
                return create_json_response(
                    {
                        "success": False,
                        "message": f"Category with ID {category_id} not found"
                    },
                    status.HTTP_404_NOT_FOUND
                )

            # Log for debugging
            logger.info(f"Category detail API: Found category: {category.name} (id: {category.id})")

            # Build the response data - use id in response
            response_data = {
                "success": True,
                "category": {
                    "id": str(category.id),  # Use the custom id field
                    "name": category.name,
                    "description": category.description,
                    "icon_url": category.icon_url,
                    "product_count": category.product_count,
                    "is_active": category.is_active,
                    "collection_id": category.collection_id
                }
            }

            # Include banner if requested and available
            if include_banner and category.banner_id:
                # Use id (not _id) in query since banner_id stores the custom id field
                banner = await Banner.find_one({"id": category.banner_id})
                if banner:
                    # Use id in response
                    response_data["category"]["banner"] = {
                        "id": str(banner.id),  # Use the custom id field
                        "title": banner.title,
                        "subtitle": banner.subtitle,
                        "image_url": banner.image_url,
                        "link": banner.link
                    }

            # Include products if requested
            if include_products:
                # Validate sort parameters
                valid_sort_fields = ["created_at", "price", "rating_avg", "sale_count", "name"]
                valid_sort_orders = ["asc", "desc"]

                if sort_by not in valid_sort_fields:
                    sort_by = "created_at"
                if sort_order not in valid_sort_orders:
                    sort_order = "desc"

                # Convert sort order to MongoDB format (1 for asc, -1 for desc)
                sort_direction = 1 if sort_order == "asc" else -1

                # Query products - use id (not _id) in query since category_ids stores the custom id field
                products = await Product.find(
                    {"category_ids": category.id, "status": "published", "in_stock": True}
                ).sort(sort_by, sort_direction).skip(products_offset).limit(products_limit).to_list()

                # Get total count for pagination - use id (not _id) in query
                total_products = await Product.find(
                    {"category_ids": category.id, "status": "published", "in_stock": True}
                ).count()

                # Debug log to help troubleshoot
                print(f"Category detail API: Found {len(products)} products for category {category.id} ({category.name}), total: {total_products}")

                formatted_products = []
                for product in products:
                    # Get brand name if available
                    brand_name = None
                    if product.brand_id:
                        # Use id (not _id) in query since brand_id stores the custom id field
                        brand = await Brand.find_one({"id": product.brand_id})
                        if brand:
                            brand_name = brand.name

                    # Format product data - use id in response
                    product_data = {
                        "id": str(product.id),  # Use the custom id field
                        "name": product.name,
                        "short_description": product.short_description,
                        "price": product.get_base_price() if hasattr(product, "get_base_price") else 0,
                        "discount_price": getattr(product, "discount_price", None),
                        "image_url": product.image_urls[0] if product.image_urls else None,
                        "rating_avg": product.rating_avg,
                        "review_count": product.review_count,
                        "in_stock": product.in_stock,
                        "is_new": product.is_new,
                        "is_bestseller": product.is_bestseller,
                        "brand_name": brand_name
                    }
                    formatted_products.append(product_data)

                response_data["products"] = formatted_products
                response_data["pagination"] = {
                    "total": total_products,
                    "limit": products_limit,
                    "offset": products_offset,
                    "has_more": (products_offset + products_limit) < total_products
                }

            # Include collection data if category belongs to a collection
            if category.collection_id:
                # Use id (not _id) in query since collection_id stores the custom id field
                collection = await Collection.find_one({"id": category.collection_id})
                if collection:
                    # Use id in response
                    response_data["category"]["collection"] = {
                        "id": str(collection.id),  # Use the custom id field
                        "name": collection.name,
                        "image_url": collection.image_url
                    }

            return create_json_response(response_data, status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error fetching category detail for {category_id}: {str(e)}", exc_info=True)
            return create_json_response(
                {
                    "success": False,
                    "message": "An error occurred while fetching category details",
                    "error": str(e) if logger.level <= logging.DEBUG else None
                },
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )