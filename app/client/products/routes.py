from fastapi import APIRouter, Request, Depends, HTTPException, Form, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Optional, List, Dict, Any
import uuid
from bson import ObjectId
from datetime import datetime
import logging
import os

from app.database import get_db
from app.models.product import Product
from app.models.review import Review, ReviewCreate
from app.client.products import templates
from app.auth.jwt import get_current_user_optional
from app.models.user import User


router = APIRouter()
logger = logging.getLogger(__name__)

# Default image path to use when product has no images
DEFAULT_IMAGE_PATH = "/static/images/product-placeholder.jpg"

# Helper function to make values JSON serializable
def make_json_serializable(obj):
    """Convert non-serializable objects to serializable format"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, (ObjectId, uuid.UUID)):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_serializable(item) for item in obj]
    return obj

# Safe database operation helper
async def safe_db_operation(operation, fallback_value=None, error_message="Database operation failed"):
    """Execute a database operation safely with error handling"""
    try:
        return await operation
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            logger.error(f"Event loop closed during database operation: {str(e)}")
            # If event loop is closed, return the fallback value
            return fallback_value
        raise
    except Exception as e:
        logger.error(f"{error_message}: {str(e)}")
        # For other exceptions, also return the fallback
        return fallback_value

@router.get("/products", response_class=HTMLResponse)
async def get_products(
    request: Request,
    category: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    sort: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    # Build the query for products
    query = {"status": "published"}
    
    # Apply category filter if provided
    if category and category != "All":
        query["tags"] = {"$regex": category, "$options": "i"}
    
    # Apply price filters if provided - using variants pricing
    # This is a simplification since variant pricing is more complex
    # A more accurate approach would require a more complex aggregation query
    
    # Decide the sort field and direction
    sort_field = "-created_at"  # Default sort by newest
    if sort == "price_low":
        sort_field = "base_price"  # Assuming base_price is indexed or calculated
    elif sort == "price_high":
        sort_field = "-base_price"
    elif sort == "rating":
        sort_field = "-rating_avg"
    elif sort == "popular":
        sort_field = "-view_count"  # Sort by popularity using view_count
    
    # Add debug logging
    logger.info(f"Fetching products with query: {query}, sort: {sort_field}")
    
    # Execute the query
    products_db = await Product.find(query).sort(sort_field).to_list()
    
    # Log the results
    logger.info(f"Found {len(products_db)} products")
    if len(products_db) > 0:
        logger.info(f"First product: {products_db[0].name}, ID: {products_db[0].id}")
    else:
        logger.warning("No products found. This may indicate a database connection issue or filtering problem.")
        # Let's verify database connection by running a basic query
        try:
            await db.command("ping")
            logger.info("Database connection is working")
        except Exception as e:
            logger.error(f"Database connection failed: {str(e)}")
    
    # Get all unique categories from the product tags
    all_tags = []
    for product in products_db:
        if product.tags:
            all_tags.extend(product.tags)
    
    # Remove duplicates using a set
    unique_tags = set(all_tags)
    
    # Format categories for display
    category_options = ["All"] + sorted(list(unique_tags))
    
    # Format products for the template
    formatted_products = []
    for product in products_db:
        # Get primary category from tags
        primary_category = product.tags[0] if product.tags and len(product.tags) > 0 else "Uncategorized"
        
        # Ensure we have at least one image or use default
        image_urls = product.image_urls or []
        if not image_urls:
            image_urls = [DEFAULT_IMAGE_PATH]
            
        # Get price from variants
        price = product.base_price
            
        formatted_products.append({
            "id": str(product.id),
            "name": product.name,
            "price": price,
            "rating": getattr(product, 'rating_avg', 0),
            "review_count": getattr(product, 'review_count', 0),
            "view_count": getattr(product, 'view_count', 0),  # Add view_count
            "category": primary_category,
            "image_urls": image_urls,
            "bestseller": getattr(product, 'is_bestseller', False),
            "new": getattr(product, 'is_new', False),
            "stock": getattr(product, 'stock', 0)
        })
    
    # Return the rendered template
    return templates.TemplateResponse(
        "products/products.html",
        {
            "request": request,
            "perfumes": formatted_products,
            "category_options": category_options,
            "current_category": category or "All",
            "min_price": min_price,
            "max_price": max_price,
            "current_sort": sort,
            "current_user": current_user if current_user else {"is_authenticated": False}
        }
    )

# Add a route for /products/ that redirects to /products to handle the trailing slash issue
@router.get("/products/", include_in_schema=False)
async def get_products_with_slash(
    request: Request,
    category: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    sort: Optional[str] = None
):
    # Construct the query string from the parameters
    query_parts = []
    if category:
        query_parts.append(f"category={category}")
    if min_price is not None:
        query_parts.append(f"min_price={min_price}")
    if max_price is not None:
        query_parts.append(f"max_price={max_price}")
    if sort:
        query_parts.append(f"sort={sort}")
    
    # Construct the redirect URL
    redirect_url = "/products"
    if query_parts:
        redirect_url += "?" + "&".join(query_parts)
    
    return RedirectResponse(url=redirect_url, status_code=302)

@router.get("/products/{product_id}", response_class=HTMLResponse)
async def get_product(
    product_id: str,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Get a single product by ID and render the detail page
    """
    try:
        # Log authentication status
        logger.info(f"User authenticated: {current_user.username if current_user else 'Anonymous'}")
        
        logger.info(f"Attempting to find product with ID: {product_id}")
        # Try to find product using multiple id fields
        product = await safe_db_operation(
            Product.find_one({"$or": [{"id": product_id}, {"_id": product_id}]}),
            fallback_value=None,
            error_message=f"Error finding product: {product_id}"
        )
    
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Increment view count
        try:
            product.view_count = getattr(product, 'view_count', 0) + 1
            await safe_db_operation(
                product.save(),
                error_message=f"Error saving view count for product {product_id}"
            )
        except Exception as e:
            # Log the error but continue processing
            logger.error(f"Error updating view count: {str(e)}")
        
        # Get primary category from tags
        primary_category = product.tags[0] if product.tags and len(product.tags) > 0 else "Uncategorized"
        
        # Ensure we have at least one image or use default
        image_urls = product.image_urls or []
        if not image_urls:
            image_urls = [DEFAULT_IMAGE_PATH]
            
        # Get price from variants
        price = getattr(product, 'base_price', 0)  # Default to 0 if missing
            
        # Format the product for the template
        formatted_product = {
            "id": str(product.id),
            "name": product.name,
            "price": price,
            "description": getattr(product, 'long_description', ''),
            "short_description": getattr(product, 'short_description', ''),
            "rating_avg": getattr(product, 'rating_avg', 0),
            "review_count": getattr(product, 'review_count', 0),
            "view_count": getattr(product, 'view_count', 0),
            "category": primary_category,
            "image_urls": image_urls,
            "bestseller": getattr(product, 'is_bestseller', False),
            "new": getattr(product, 'is_new', False),
            "key_notes": product.tags,
            "details": {},  # Initialize as empty dict and fill it properly
            "stock": getattr(product, 'stock', 0),
            "is_perfume": getattr(product, 'is_perfume', False)
        }
            
        # Convert variants to JSON serializable format
        if hasattr(product, 'variants') and product.variants:
            details = {}
            for variant_type, variants in product.variants.items():
                details[variant_type] = []
                for variant in variants:
                    if hasattr(variant, 'dict'):
                        # Use the model's built-in dict method if available
                        variant_dict = variant.dict()
                        details[variant_type].append(variant_dict)
                    elif hasattr(variant, '__dict__'):
                        # Create a dict from the variant's attributes
                        variant_dict = {
                            "id": getattr(variant, 'id', str(uuid.uuid4())),
                            "value": getattr(variant, 'value', ''),
                            "price": getattr(variant, 'price', 0)
                        }
                        details[variant_type].append(variant_dict)
                    elif isinstance(variant, dict):
                        # Already a dict, just append it
                        details[variant_type].append(variant)
                
            formatted_product["details"] = details
            
        # Fetch scent information if product is a perfume with safe operation
        if getattr(product, 'is_perfume', False) and hasattr(product, 'scent_ids') and product.scent_ids:
            try:
                from app.models.scent import Scent
                scents = await safe_db_operation(
                    Scent.find({"id": {"$in": product.scent_ids}}).to_list(),
                    fallback_value=[],
                    error_message=f"Error fetching scent information for product {product_id}"
                )
                formatted_scents = []
                for scent in scents:
                    formatted_scents.append({
                        "id": scent.id,
                        "name": scent.name,
                        "description": getattr(scent, 'description', '')
                    })
                formatted_product["scents"] = formatted_scents
            except Exception as e:
                logger.error(f"Error fetching scent information: {e}")
            
        # Fetch similar products based on tags or brand with safe operation
        similar_products = []
        if product.tags and len(product.tags) > 0:
            # Find products that share at least one tag with the current product
            product_id_field = "_id" if hasattr(product, "_id") else "id"
            product_id_value = product._id if hasattr(product, "_id") else product.id
                
            tag_query = {"$and": [
                {product_id_field: {"$ne": product_id_value}},  # Exclude current product
                {"tags": {"$in": product.tags}},
                {"status": "published"}
            ]}
            similar_products = await safe_db_operation(
                Product.find(tag_query).limit(4).to_list(),
                fallback_value=[],
                error_message=f"Error fetching similar products by tags for product {product_id}"
            )
            
        # If no similar products found by tags, try fetching from the same brand
        if not similar_products and hasattr(product, 'brand_id') and product.brand_id:
            product_id_field = "_id" if hasattr(product, "_id") else "id"
            product_id_value = product._id if hasattr(product, "_id") else product.id
                
            brand_query = {"$and": [
                {product_id_field: {"$ne": product_id_value}},  # Exclude current product
                {"brand_id": product.brand_id},
                {"status": "published"}
            ]}
            similar_products = await safe_db_operation(
                Product.find(brand_query).limit(4).to_list(),
                fallback_value=[],
                error_message=f"Error fetching similar products by brand for product {product_id}"
            )
        
        # Format related products
        formatted_related = []
        for rel_product in similar_products:
            # Get primary category for related product
            rel_primary_category = rel_product.tags[0] if rel_product.tags and len(rel_product.tags) > 0 else "Uncategorized"
            
            # Ensure related products have at least one image
            rel_image_urls = rel_product.image_urls or []
            if not rel_image_urls:
                rel_image_urls = [DEFAULT_IMAGE_PATH]
                
            # Get price from variants for related product
            rel_price = getattr(rel_product, 'base_price', 0)
                
            # Format the related product details
            rel_details = {}
            if hasattr(rel_product, 'variants') and rel_product.variants:
                for variant_type, variants in rel_product.variants.items():
                    rel_details[variant_type] = []
                    for variant in variants:
                        if hasattr(variant, 'dict'):
                            variant_dict = variant.dict()
                            rel_details[variant_type].append(variant_dict)
                        elif hasattr(variant, '__dict__'):
                            variant_dict = {
                                "id": getattr(variant, 'id', str(uuid.uuid4())),
                                "value": getattr(variant, 'value', ''),
                                "price": getattr(variant, 'price', 0)
                            }
                            rel_details[variant_type].append(variant_dict)
                        elif isinstance(variant, dict):
                            rel_details[variant_type].append(variant)
                
            formatted_related.append({
                "id": str(rel_product.id),
                "name": rel_product.name,
                "price": rel_price,
                "rating_avg": getattr(rel_product, 'rating_avg', 0),
                "review_count": getattr(rel_product, 'review_count', 0),
                "view_count": getattr(rel_product, 'view_count', 0),
                "category": rel_primary_category,
                "image_urls": rel_image_urls,
                "bestseller": getattr(rel_product, 'is_bestseller', False),
                "new": getattr(rel_product, 'is_new', False),
                "stock": getattr(rel_product, 'stock', 0),
                "details": rel_details
            })
            
        # Return the rendered template with serializable data
        return templates.TemplateResponse(
            "products/product_detail.html",
            {
                "request": request,
                "product": make_json_serializable(formatted_product),
                "related_products": make_json_serializable(formatted_related),
                "current_user": current_user if current_user else {"is_authenticated": False}
            }
        )
    except HTTPException:
        # Rethrow HTTP exceptions
        raise
    except Exception as e:
        logger.exception(f"Error in get_product for ID {product_id}: {str(e)}")
        # Return a friendly error page
        return templates.TemplateResponse(
            "products/product_detail.html",
            {
                "request": request,
                "error": "Product could not be loaded. Please try again later.",
                "product": {
                    "name": "Product Not Available", 
                    "image_urls": [DEFAULT_IMAGE_PATH], 
                    "price": 0,
                    "stock": 0,
                    "details": {},
                    "tags": [],
                    "rating_avg": 0,
                    "review_count": 0,
                    "is_bestseller": False,
                    "is_new": False,
                    "view_count": 0
                },
                "related_products": [],
                "current_user": current_user if current_user else {"is_authenticated": False}
            },
            status_code=500
        )

@router.get("/product/{product_id}", include_in_schema=False)
async def redirect_product_detail(product_id: str):
    """
    Redirect from /product/{id} to /products/{id} to handle legacy URLs
    """
    logger.info(f"Redirecting from /product/{product_id} to /products/{product_id}")
    return RedirectResponse(url=f"/products/{product_id}", status_code=301)

@router.get("/products/{product_id}/reviews", response_class=JSONResponse)
async def get_product_reviews(
    product_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    Get reviews for a specific product
    """
    try:
        # Check if product exists using multiple ID fields
        product = await safe_db_operation(
            Product.find_one({"$or": [{"id": product_id}, {"_id": product_id}]}),
            fallback_value=None,
            error_message=f"Error finding product: {product_id}"
        )
        
        if not product:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Product not found"}
            )
        
        # Get reviews for the product
        reviews = await safe_db_operation(
            Review.get_by_product(product_id),
            fallback_value=[],
            error_message=f"Error fetching reviews for product: {product_id}"
        )
        
        # Calculate rating statistics
        rating_stats = await safe_db_operation(
            Review.calculate_product_rating(product_id),
            fallback_value={"rating_avg": 0, "review_count": 0, "rating_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}},
            error_message=f"Error calculating rating statistics for product: {product_id}"
        )
        
        # Format reviews for the response
        formatted_reviews = []
        for review in reviews:
            # Get user if available
            user = None
            if review.user_id:
                user = await safe_db_operation(
                    review.get_user(),
                    fallback_value=None,
                    error_message=f"Error fetching user for review: {review.id}"
                )
            
            formatted_review = {
                "id": review.id,
                "rating": review.rating,
                "content": review.content,
                "photo_urls": review.photo_urls,
                "helpful_votes": review.helpful_votes,
                "verified_purchase": review.verified_purchase,
                "created_at": review.created_at.isoformat() if review.created_at else None,
                "user": {
                    "id": user.id if user else None,
                    "name": user.name if user else review.user_name or "Anonymous"
                }
            }
            formatted_reviews.append(formatted_review)
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "reviews": formatted_reviews,
                "stats": rating_stats
            }
        )
    except Exception as e:
        logger.exception(f"Error in get_product_reviews for product {product_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Failed to fetch reviews"}
        )

@router.post("/products/{product_id}/reviews", response_class=JSONResponse)
async def add_product_review(
    product_id: str,
    rating: int = Form(...),
    content: Optional[str] = Form(None),
    user_name: Optional[str] = Form(None),
    is_rating_only: Optional[str] = Form(None),
    photos: List[UploadFile] = [],
    request: Request = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Add a new review for a product
    """
    try:
        # Get user ID if authenticated
        user_id = None
        if current_user:
            user_id = current_user.id
            logger.info(f"Review submitted by authenticated user: {current_user.username} (ID: {user_id})")
        else:
            logger.info("Review submitted by anonymous user")
            
        # Check if product exists using multiple ID fields
        product = await safe_db_operation(
            Product.find_one({"$or": [{"id": product_id}, {"_id": product_id}]}),
            fallback_value=None,
            error_message=f"Error finding product: {product_id}"
        )
        
        if not product:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Product not found"}
            )
        
        # Check if this is a rating-only submission
        is_rating_only_submission = is_rating_only == "true"
        
        # Validate fields based on submission type
        if not is_rating_only_submission:
            # For full reviews, require content
            if not content or not content.strip():
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "message": "Review content is required"}
                )
        
        # If user is not logged in, require a name
        if not user_id and not user_name:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Please provide your name"}
            )
        
        # Check if user already reviewed this product
        if user_id:
            existing_review = await safe_db_operation(
                Review.find_one({"product_id": product_id, "user_id": user_id}),
                fallback_value=None,
                error_message=f"Error checking existing review"
            )
            
            if existing_review:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "message": "You have already reviewed this product"}
                )
        
        # Process photo uploads using the new validate_and_save_review_image function
        photo_urls = []
        if photos:
            # Import the function
            from app.utils.image import validate_and_save_review_image
            
            # Limit to 5 photos
            max_photos = 5
            photos = photos[:max_photos]
            
            # Process each photo
            for photo in photos:
                try:
                    # Upload to Cloudinary and get URL
                    photo_url = await validate_and_save_review_image(photo)
                    if photo_url:
                        photo_urls.append(photo_url)
                except Exception as e:
                    logger.error(f"Error saving review photo: {str(e)}")
        
        # For rating-only submissions, set content to empty string if not provided
        if is_rating_only_submission and (not content or not content.strip()):
            content = ""
        
        # Create review data
        review_data = {
            "product_id": product_id,
            "rating": rating,
            "content": content or "",
            "photo_urls": photo_urls,
            "verified_purchase": False  # This could be checked against order history
        }
        
        # Add user information based on what's available
        if user_id:
            review_data["user_id"] = user_id
        elif user_name:
            review_data["user_name"] = user_name
        
        # Create and save review
        review = Review(**review_data)
        await safe_db_operation(
            review.save(),
            error_message=f"Error saving review for product: {product_id}"
        )
        
        # Update product rating
        rating_stats = await safe_db_operation(
            Review.calculate_product_rating(product_id),
            fallback_value={"rating_avg": 0.0, "review_count": 0, "rating_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}},
            error_message=f"Error calculating rating statistics for product: {product_id}"
        )
        
        # Update product fields with the new rating
        product.rating_avg = rating_stats["rating_avg"]
        product.review_count = rating_stats["review_count"]
        
        await safe_db_operation(
            product.save(),
            error_message=f"Error updating product rating: {product_id}"
        )
        
        # Return success response
        return JSONResponse(
            status_code=201,
            content={
                "success": True,
                "message": "Review added successfully",
                "review": {
                    "id": review.id,
                    "rating": review.rating,
                    "content": review.content,
                    "photo_urls": review.photo_urls,
                    "helpful_votes": review.helpful_votes,
                    "created_at": review.created_at.isoformat() if review.created_at else None
                },
                "updated_stats": rating_stats
            }
        )
    except ValueError as ve:
        logger.error(f"Validation error in add_product_review: {str(ve)}")
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": str(ve)}
        )
    except Exception as e:
        logger.exception(f"Error in add_product_review for product {product_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Failed to add review"}
        )

@router.post("/products/{product_id}/reviews/helpful", response_class=JSONResponse)
async def mark_review_helpful(
    product_id: str,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Mark a review as helpful
    """
    try:
        # Log user if authenticated
        if current_user:
            logger.info(f"Helpful vote from authenticated user: {current_user.username}")
        else:
            logger.info("Helpful vote from anonymous user")
            
        # Parse request body
        data = await request.json()
        review_id = data.get("review_id")
        
        if not review_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Review ID is required"}
            )
        
        # Find the review - try all possible combinations of id fields
        logger.info(f"Finding review with ID: {review_id} for product {product_id}")
        
        # First try direct ID match
        review = await safe_db_operation(
            Review.find_one({"id": review_id, "product_id": product_id}),
            fallback_value=None,
            error_message=f"Error finding review: {review_id}"
        )
        
        # If not found, try with MongoDB _id
        if not review:
            logger.info(f"Review not found with id, trying with _id")
            review = await safe_db_operation(
                Review.find_one({"_id": review_id, "product_id": product_id}),
                fallback_value=None,
                error_message=f"Error finding review with _id: {review_id}"
            )
            
        # If still not found, try just with ID fields without product_id constraint
        if not review:
            logger.info(f"Review not found with product constraint, trying just ID")
            review = await safe_db_operation(
                Review.find_one({"$or": [{"id": review_id}, {"_id": review_id}]}),
                fallback_value=None,
                error_message=f"Error finding review by any ID: {review_id}"
            )
        
        if not review:
            logger.error(f"Review not found with any ID format: {review_id}")
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Review not found"}
            )
        
        # Increment helpful_votes
        review.helpful_votes = (review.helpful_votes or 0) + 1
        logger.info(f"Incrementing helpful votes for review {review_id} to {review.helpful_votes}")
        
        # Save the review
        await safe_db_operation(
            review.save(),
            error_message=f"Error updating helpful votes for review: {review_id}"
        )
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Thanks for your feedback!",
                "helpful_votes": review.helpful_votes
            }
        )
    except Exception as e:
        logger.exception(f"Error in mark_review_helpful: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Failed to mark review as helpful"}
    ) 