from typing import Optional, List
from datetime import datetime, timedelta
from uuid import uuid4
import re
import json
import traceback
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from app.database import get_db
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.models.user import User
from app.auth.jwt import get_current_active_admin
from app.models.product import Product
from app.models.category import Category
from app.models.collection import Collection
from app.models.brand import Brand
from app.models.scent import Scent
from app.utils.image import validate_and_optimize_product_image, delete_images, delete_image  # Import the specific delete_image function
from app.utils.json import to_serializable_dict  # Import our custom JSON serializer

# Get router and templates from the package
from app.admin.products import router, templates

@router.get("/")
async def list_products(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    """
    List all products 
    """
    # Use MongoDB aggregation to get products with related data
    products = await Product.find().to_list()
    
    # Convert products to serializable dict format that handles datetime objects
    serialized_products = [to_serializable_dict(product) for product in products]
    
    return templates.TemplateResponse(
        "products/list.html",
        {"request": request, "products": serialized_products, "user": current_user}
    )

@router.get("/new")
async def create_product_form(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Display product creation form
    """
    # Get all active categories
    categories = await Category.find({"is_active": True}).to_list()
    
    # Get all active collections
    collections = await Collection.find({"is_active": True}).to_list()
    
    # Get all brands sorted by name
    brands = await Brand.find().sort("name").to_list()
    
    # Get all active scents
    scents = await Scent.find({"is_active": True}).sort("name").to_list()
    
    return templates.TemplateResponse(
        "products/create.html",
        {
            "request": request, 
            "user": current_user, 
            "error": None, 
            "categories": categories,
            "collections": collections,
            "brands": brands,
            "scents": scents
        }
    )

@router.post("/new")
async def create_product(
    request: Request,
    name: str = Form(...),
    long_description: str = Form(...),
    short_description: Optional[str] = Form(None),
    in_stock: bool = Form(False),
    stock_quantity: int = Form(0),
    images: List[UploadFile] = File(...),
    brand_id: Optional[str] = Form(None),
    category_ids: List[str] = Form([]),
    tags: Optional[str] = Form(None),
    status: str = Form("published"),
    featured: bool = Form(False),
    is_perfume: bool = Form(False),
    scent_id: Optional[str] = Form(None),
    variant_types: List[str] = Form([]),
    variant_values: List[str] = Form([]),
    variant_prices: List[float] = Form([]),
    current_user: User = Depends(get_current_active_admin)
):
    """
    Create a new product with MongoDB
    """
    try:
        # Validate and optimize images, then upload to Cloudinary
        image_urls = []
        for image in images:
            if image.filename:  # Check if file was actually uploaded
                image_url = await validate_and_optimize_product_image(image)
                image_urls.append(image_url)
                if len(image_urls) >= 10:  # Limit to 10 images
                    break
        
        if not image_urls:
            raise HTTPException(
                status_code=400,
                detail="At least one image is required"
            )
        
        # Process tags
        tag_list = []
        if tags:
            tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
        
        # Process variants
        variants = {}
        if variant_types and variant_values and variant_prices and len(variant_types) == len(variant_values) == len(variant_prices):
            for i in range(len(variant_types)):
                if variant_types[i] not in variants:
                    variants[variant_types[i]] = []
                variants[variant_types[i]].append({
                    "id": str(uuid4()),
                    "value": variant_values[i],
                    "price": int(float(variant_prices[i]) * 100)  # Convert to cents
                })
        else:
            # If no variants provided, raise an error since we need at least one variant with a price
            raise HTTPException(
                status_code=400,
                detail="At least one variant with price is required"
            )
        
        # Create product with MongoDB document
        product_data = {
            "id": str(uuid4()),
            "name": name,
            "short_description": short_description,
            "long_description": long_description,
            "stock": stock_quantity,
            "in_stock": in_stock or stock_quantity > 0,
            "image_urls": image_urls,
            "variants": variants,
            "brand_id": brand_id if brand_id and brand_id.strip() else None,
            "category_ids": [cat_id for cat_id in category_ids if cat_id and cat_id.strip()],
            "tags": tag_list,
            "status": status,
            "featured": featured,
            "is_perfume": is_perfume,
            "scent_id": scent_id if scent_id and scent_id.strip() else None,
            "last_restocked": datetime.now(),
            "total_stock_lifetime": stock_quantity,
            "in_transit": 0,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        
        # Insert product using Beanie ODM
        product = Product(**product_data)
        await product.save()
        
        # Update product count for categories
        if product.category_ids:
            for cat_id in product.category_ids:
                try:
                    category = await Category.find_one({"id": cat_id})
                    if category:
                        category.product_count += 1
                        await category.save()
                except Exception as e:
                    print(f"Error updating category count: {str(e)}")
                    continue
        
        # Redirect to product list
        return RedirectResponse(
            url="/admin/products/",
            status_code=303
        )
    except HTTPException as he:
        # Get lists for dropdowns in case of error
        categories = await Category.find({"is_active": True}).to_list()
        brands = await Brand.find().sort("name").to_list()
        collections = await Collection.find({"is_active": True}).to_list()
        scents = await Scent.find({"is_active": True}).sort("name").to_list()
        
        return templates.TemplateResponse(
            "products/create.html",
            {
                "request": request,
                "error": he.detail,
                "user": current_user,
                "categories": categories,
                "brands": brands,
                "collections": collections,
                "scents": scents
            },
            status_code=he.status_code
        )
    except Exception as e:
        # Log the error for debugging
        print(f"Error creating product: {str(e)}")
        print(traceback.format_exc())
        
        # Get lists for dropdowns in case of error
        categories = await Category.find({"is_active": True}).to_list()
        brands = await Brand.find().sort("name").to_list()
        collections = await Collection.find({"is_active": True}).to_list()
        scents = await Scent.find({"is_active": True}).sort("name").to_list()
        
        return templates.TemplateResponse(
            "products/create.html",
            {
                "request": request,
                "error": f"Could not create product: {str(e)}",
                "user": current_user,
                "categories": categories,
                "brands": brands,
                "collections": collections,
                "scents": scents
            },
            status_code=500
        )
   
@router.get("/{product_id}")
async def view_product(
    request: Request,
    product_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    View a single product's details
    """
    try:
        # Attempt to find product by ID
        product = await Product.find_one({"_id": product_id})
        
        if not product:
            raise HTTPException(status_code=404, detail=f"Product with ID {product_id} not found")
        
        # Get categories from DB
        categories = await Category.find({"is_active": True}).to_list()
        
        # Get related data
        brand = await product.get_brand()
        scent = await product.get_scent()
        
        return templates.TemplateResponse(
            "products/detail.html",
            {
                "request": request,
                "product": product,
                "user": current_user,
                "categories": categories,
                "brand": brand,
                "scent": scent
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "products/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Error loading product: {str(e)}"
            },
            status_code=500
        )

@router.get("/{product_id}/edit")
async def edit_product_form(
    request: Request,
    product_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Display product edit form
    """
    try:
        # Attempt to find product by ID
        product = await Product.find_one({"id": product_id})
        
        if not product:
            raise HTTPException(status_code=404, detail=f"Product with ID {product_id} not found")
        
        # Get all necessary data for dropdowns
        categories = await Category.find({"is_active": True}).to_list()
        collections = await Collection.find({"is_active": True}).to_list()
        brands = await Brand.find().sort("name").to_list()
        scents = await Scent.find({"is_active": True}).sort("name").to_list()
        
        return templates.TemplateResponse(
            "products/edit.html",
            {
                "request": request,
                "product": product,
                "user": current_user,
                "error": None,
                "categories": categories,
                "collections": collections,
                "brands": brands,
                "scents": scents
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "products/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Error loading product: {str(e)}"
            },
            status_code=500
        )

@router.post("/{product_id}/edit")
async def edit_product(
    request: Request,
    product_id: str,
    name: str = Form(...),
    long_description: str = Form(...),
    short_description: Optional[str] = Form(None),
    in_stock: bool = Form(False),
    stock_quantity: int = Form(0),
    brand_id: Optional[str] = Form(None),
    category_ids: List[str] = Form([]),
    tags: Optional[str] = Form(None),
    status: str = Form("published"),
    featured: bool = Form(False),
    collection_id: Optional[str] = Form(None),
    is_perfume: bool = Form(False),
    scent_ids: List[str] = Form([]),
    variant_types: List[str] = Form([]),
    variant_values: List[str] = Form([]),
    variant_prices: List[float] = Form([]),
    variant_ids: List[Optional[str]] = Form([]),
    current_user: User = Depends(get_current_active_admin)
):
    """
    Update an existing product (excluding images which are handled by separate endpoints)
    """
    try:
        # Attempt to find product by ID
        product = await Product.find_one({"id": product_id})
        
        if not product:
            raise HTTPException(status_code=404, detail=f"Product with ID {product_id} not found")
        
        # Create a map of existing variants to preserve IDs
        existing_variants = {}
        if product.variants:
            for vtype, variants in product.variants.items():
                existing_variants[vtype] = {}
                for v in variants:
                    # Use the value as key to match with form data
                    existing_variants[vtype][v.value] = v.id
        
        # Process variants
        variants = {}
        if variant_types and variant_values and variant_prices and len(variant_types) == len(variant_values) == len(variant_prices):
            for i in range(len(variant_types)):
                if variant_types[i] not in variants:
                    variants[variant_types[i]] = []
                
                # Use existing variant ID if available, otherwise generate a new one
                variant_id = None
                # Check if we have an ID in the form data
                if i < len(variant_ids) and variant_ids[i]:
                    variant_id = variant_ids[i]
                # Otherwise check if we can find a matching variant by type and value
                elif variant_types[i] in existing_variants and variant_values[i] in existing_variants[variant_types[i]]:
                    variant_id = existing_variants[variant_types[i]][variant_values[i]]
                # Generate a new ID if no existing ID found
                if not variant_id:
                    variant_id = str(uuid4())
                
                variants[variant_types[i]].append({
                    "id": variant_id,
                    "value": variant_values[i],
                    "price": int(float(variant_prices[i])),  # Already in cents
                })
        else:
            # If no variants provided, raise an error since we need at least one variant with a price
            raise HTTPException(
                status_code=400,
                detail="At least one variant with price is required"
            )
        
        # Process tags
        tag_list = []
        if tags:
            tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
        
        # Update product fields
        product.name = name
        product.short_description = short_description
        product.long_description = long_description
        product.in_stock = in_stock or stock_quantity > 0
        product.stock = stock_quantity
        product.brand_id = brand_id if brand_id and brand_id.strip() else None
        product.collection_id = collection_id if collection_id and collection_id.strip() else None
        product.category_ids = [cat_id for cat_id in category_ids if cat_id and cat_id.strip()]
        product.tags = tag_list
        product.status = status
        product.featured = featured
        product.is_perfume = is_perfume
        product.scent_ids = [scent_id for scent_id in scent_ids if scent_id and scent_id.strip()]
        product.variants = variants
        product.updated_at = datetime.now()
        
        # Check if we have at least one image
        if not product.image_urls or len(product.image_urls) == 0:
            raise HTTPException(
                status_code=400,
                detail="Product must have at least one image"
            )
        
        # Save the updated product
        await product.save()
        
        # Redirect to product detail page
        return RedirectResponse(
            url=f"/admin/products/{product_id}",
            status_code=303
        )
    except HTTPException as he:
        # Get data for dropdowns in case of error
        categories = await Category.find({"is_active": True}).to_list()
        brands = await Brand.find().sort("name").to_list()
        collections = await Collection.find({"is_active": True}).to_list()
        scents = await Scent.find({"is_active": True}).sort("name").to_list()
        
        return templates.TemplateResponse(
            "products/edit.html",
            {
                "request": request,
                "product": product,
                "error": he.detail,
                "user": current_user,
                "categories": categories,
                "brands": brands,
                "collections": collections,
                "scents": scents
            },
            status_code=he.status_code
        )
    except Exception as e:
        # Log the error for debugging
        print(f"Error updating product: {str(e)}")
        print(traceback.format_exc())
        
        # Get data for dropdowns in case of error
        categories = await Category.find({"is_active": True}).to_list()
        brands = await Brand.find().sort("name").to_list()
        collections = await Collection.find({"is_active": True}).to_list()
        scents = await Scent.find({"is_active": True}).sort("name").to_list()
        
        return templates.TemplateResponse(
            "products/edit.html",
            {
                "request": request,
                "product": product,
                "error": f"Could not update product: {str(e)}",
                "user": current_user,
                "categories": categories,
                "brands": brands,
                "collections": collections,
                "scents": scents
            },
            status_code=500
        )

@router.get("/{product_id}/delete")
async def delete_product(
    product_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Delete a product
    """
    try:
        # Attempt to find product by ID
        product = await Product.find_one({"id": product_id})
        
        if not product:
            raise HTTPException(status_code=404, detail=f"Product with ID {product_id} not found")
        
        # Delete images from Cloudinary if they exist
        if product.image_urls:
            # Use our new delete_images function
            result = delete_images(product.image_urls)
            print(f"Deleted {result['success']} images, failed to delete {result['failed']} images")
        
        # Delete the product
        await product.delete()
        
        # Update category product counts
        if product.category_ids:
            for cat_id in product.category_ids:
                try:
                    category = await Category.find_one({"id": cat_id})
                    if category and category.product_count > 0:
                        category.product_count -= 1
                        await category.save()
                except Exception:
                    # Continue even if updating count fails
                    pass
        
        # Redirect to product list
        return RedirectResponse(
            url="/admin/products/",
            status_code=303  # Use the numeric status code directly
        )
    except Exception as e:
        # Log the error for debugging
        print(f"Error deleting product: {str(e)}")
        print(traceback.format_exc())
        
        return templates.TemplateResponse(
            "products/error.html",
            {
                "request": Request,
                "user": current_user,
                "error": f"Could not delete product: {str(e)}"
            },
            status_code=500
        )

@router.post("/{product_id}/restock")
async def restock_product(
    product_id: str,
    quantity: dict,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Restock a product with the specified quantity
    """
    try:
        # Find the product
        product = await Product.find_one({"_id": product_id})
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Get the quantity from the request body
        restock_quantity = quantity.get("quantity", 0)
        if restock_quantity < 0:
            raise HTTPException(status_code=400, detail="Quantity must be positive")
        
        # Update product stock information
        product.stock += restock_quantity
        product.total_stock_lifetime += restock_quantity
        product.last_restocked = datetime.now()
        
        # If product was out of stock, mark it as in stock
        if product.stock > 0:
            product.in_stock = True
        
        # Save the updated product
        await product.save()
        
        # Return updated stock information
        return JSONResponse({
            "current_stock": product.stock,
            "in_transit": product.in_transit,
            "last_restocked": product.last_restocked.isoformat(),
            "total_stock_lifetime": product.total_stock_lifetime
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Could not restock product: {str(e)}"
        )

@router.post("/{product_id}/update-stock")
async def update_stock(
    product_id: str,
    stock_data: dict,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Update product stock information
    """
    try:
        # Find the product
        product = await Product.find_one({"_id": product_id})
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Update stock and in_transit values
        new_stock = stock_data.get("stock")
        new_in_transit = stock_data.get("in_transit")
        
        if new_stock is not None:
            if new_stock < 0:
                raise HTTPException(status_code=400, detail="Stock cannot be negative")
            product.stock = new_stock
            product.in_stock = new_stock > 0
        
        if new_in_transit is not None:
            if new_in_transit < 0:
                raise HTTPException(status_code=400, detail="In-transit quantity cannot be negative")
            product.in_transit = new_in_transit
        
        # Save the updated product
        await product.save()
        
        return JSONResponse({
            "current_stock": product.stock,
            "in_transit": product.in_transit,
            "in_stock": product.in_stock
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Could not update stock: {str(e)}"
        )

@router.get("/{product_id}/stock")
async def get_stock_info(
    product_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Get current stock information for a product
    """
    # Find the product
    product = await Product.find_one({"_id": product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return JSONResponse({
        "current_stock": product.stock,
        "in_transit": product.in_transit,
        "last_restocked": product.last_restocked.isoformat() if product.last_restocked else None,
        "total_stock_lifetime": product.total_stock_lifetime,
        "in_stock": product.in_stock
    })

@router.post("/{product_id}/transit")
async def update_transit(
    product_id: str,
    transit_data: dict,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Update the in-transit quantity for a product
    """
    try:
        # Find the product
        product = await Product.find_one({"_id": product_id})
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        in_transit = transit_data.get("in_transit")
        if in_transit is None:
            raise HTTPException(status_code=400, detail="In-transit quantity is required")
        if in_transit < 0:
            raise HTTPException(status_code=400, detail="In-transit quantity cannot be negative")
        
        product.in_transit = in_transit
        await product.save()
        
        return JSONResponse({
            "in_transit": product.in_transit
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Could not update in-transit quantity: {str(e)}"
        )

@router.post("/{product_id}/receive-transit")
async def receive_transit(
    product_id: str,
    receive_data: dict,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Receive products from transit into stock
    """
    try:
        # Find the product
        product = await Product.find_one({"_id": product_id})
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        quantity = receive_data.get("quantity")
        if quantity is None:
            raise HTTPException(status_code=400, detail="Quantity is required")
        if quantity < 0:
            raise HTTPException(status_code=400, detail="Quantity cannot be negative")
        if quantity > product.in_transit:
            raise HTTPException(status_code=400, detail="Received quantity cannot exceed in-transit quantity")
        
        # Update stock and in-transit quantities
        product.stock += quantity
        product.in_transit -= quantity
        product.total_stock_lifetime += quantity
        product.last_restocked = datetime.now()
        
        # If product was out of stock, mark it as in stock
        if product.stock > 0:
            product.in_stock = True
        
        # Save the updated product
        await product.save()
        
        return JSONResponse({
            "current_stock": product.stock,
            "in_transit": product.in_transit,
            "last_restocked": product.last_restocked.isoformat(),
            "total_stock_lifetime": product.total_stock_lifetime,
            "in_stock": product.in_stock
        })
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Could not receive transit: {str(e)}"
        )

@router.post("/{product_id}/discount")
async def update_discount(
    request: Request,
    product_id: str,
    old_price: Optional[str] = Form(None),
    discount_price: Optional[str] = Form(None),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    current_user: User = Depends(get_current_active_admin)
):
    """
    Update discount information for a product
    """
    try:
        print(f"Updating discount for product ID: {product_id}")
        form_data = await request.form()
        print(f"Form data: {dict(form_data)}")
        
        # Find the product
        print(f"Looking for product with id: {product_id}")
        product = await Product.find_one({"_id": product_id})
        
        # If not found by id, try _id (in case MongoDB is using _id instead)
        if not product:
            print(f"Product not found by id, trying _id...")
            try:
                from bson import ObjectId
                if ObjectId.is_valid(product_id):
                    product = await Product.find_one({"_id": ObjectId(product_id)})
                    print(f"Product found by _id: {product is not None}")
            except Exception as e:
                print(f"Error when searching by _id: {e}")
                
        if not product:
            print(f"Product not found with ID: {product_id}")
            raise HTTPException(status_code=404, detail="Product not found")
        
        print(f"Product found: {product.name}")
        
        # Calculate discount percentage
        if old_price and discount_price:
            original_price = float(old_price)
            new_price = float(discount_price)
            
            if new_price >= original_price:
                raise HTTPException(status_code=400, detail="Discount price must be less than original price")
                
            discount_percentage = round(100 - (new_price / original_price * 100), 2)
            print(f"Calculated discount percentage: {discount_percentage}%")
            
            # Update product discount info
            product.discount_percentage = discount_percentage
            
            # Parse optional date parameters
            if start_date:
                try:
                    product.discount_start_date = datetime.fromisoformat(start_date)
                except ValueError:
                    product.discount_start_date = datetime.now()
            else:
                product.discount_start_date = datetime.now()
                
            if end_date:
                try:
                    product.discount_end_date = datetime.fromisoformat(end_date)
                except ValueError:
                    product.discount_end_date = datetime.now() + timedelta(days=30)
            else:
                product.discount_end_date = datetime.now() + timedelta(days=30)
                
            print(f"Discount period: {product.discount_start_date} to {product.discount_end_date}")
            
            # Save the updated product
            print(f"Saving product with updated discount...")
            await product.save()
            print(f"Product saved successfully")
            
            # Determine if this is an API request or form submission
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JSONResponse(
                    content={
                        "success": True,
                        "message": f"Discount of {discount_percentage}% applied successfully to {product.name}",
                        "product_id": product_id,
                        "discount_percentage": discount_percentage
                    }
                )
            else:
                return templates.TemplateResponse(
                    "dashboard/products.html",
                    {
                        "request": request,
                        "current_user": current_user,
                        "success_message": f"Discount of {discount_percentage}% applied successfully to {product.name}"
                    }
                )
        else:
            print(f"Missing required parameters: old_price={old_price}, discount_price={discount_price}")
            raise HTTPException(status_code=400, detail="Both old price and discount price are required")
            
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error in update_discount: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Could not update discount: {str(e)}"
        )

@router.get("/{product_id}/variants")
async def get_product_variants(
    product_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    """
    Get all variants for a product by ID
    """
    try:
        # First try to find by exact ID match
        product = await Product.find_one({"_id": product_id})
        
        # If not found by id, try _id
        if product is None:
            try:
                from bson import ObjectId
                if ObjectId.is_valid(product_id):
                    product = await Product.find_one({"_id": ObjectId(product_id)})
            except Exception as e:
                print(f"Error when searching by _id: {e}")
        
        if not product:
            return JSONResponse(
                content={
                    "success": False,
                    "message": f"Product not found with ID: {product_id}"
                },
                status_code=404
            )
            
        # Check if product has variants
        if not product.variants:
            return JSONResponse(
                content={
                    "success": True,
                    "message": "Product has no variants",
                    "variants": {},
                    "product_name": product.name
                }
            )
        
        # Process variants into a more usable format
        processed_variants = {}
        
        for variant_type, variants in product.variants.items():
            processed_variants[variant_type] = []
            
            for variant in variants:
                # Handle different variant formats
                variant_dict = {}
                
                # Get variant ID
                if hasattr(variant, 'id'):
                    variant_dict["id"] = str(variant.id)
                elif isinstance(variant, dict) and 'id' in variant:
                    variant_dict["id"] = str(variant['id'])
                else:
                    variant_dict["id"] = "unknown"
                
                # Get variant value
                if hasattr(variant, 'value'):
                    variant_dict["value"] = variant.value
                elif isinstance(variant, dict) and 'value' in variant:
                    variant_dict["value"] = variant['value']
                else:
                    variant_dict["value"] = "unknown"
                
                # Get variant price
                if hasattr(variant, 'price'):
                    variant_dict["price"] = variant.price
                elif isinstance(variant, dict) and 'price' in variant:
                    variant_dict["price"] = variant['price']
                else:
                    variant_dict["price"] = 0
                
                # Get discount information if available
                if hasattr(variant, 'discount_percentage'):
                    variant_dict["discount_percentage"] = variant.discount_percentage
                elif isinstance(variant, dict) and 'discount_percentage' in variant:
                    variant_dict["discount_percentage"] = variant['discount_percentage']
                
                # Get discount dates if available
                if hasattr(variant, 'discount_start_date'):
                    variant_dict["discount_start_date"] = variant.discount_start_date.isoformat() if variant.discount_start_date else None
                elif isinstance(variant, dict) and 'discount_start_date' in variant:
                    variant_dict["discount_start_date"] = variant['discount_start_date'].isoformat() if variant['discount_start_date'] else None
                
                if hasattr(variant, 'discount_end_date'):
                    variant_dict["discount_end_date"] = variant.discount_end_date.isoformat() if variant.discount_end_date else None
                elif isinstance(variant, dict) and 'discount_end_date' in variant:
                    variant_dict["discount_end_date"] = variant['discount_end_date'].isoformat() if variant['discount_end_date'] else None
                
                # Get quantity limit information if available
                if hasattr(variant, 'discount_quantity_limit'):
                    variant_dict["discount_quantity_limit"] = variant.discount_quantity_limit
                elif isinstance(variant, dict) and 'discount_quantity_limit' in variant:
                    variant_dict["discount_quantity_limit"] = variant['discount_quantity_limit']
                
                if hasattr(variant, 'discount_quantity_used'):
                    variant_dict["discount_quantity_used"] = variant.discount_quantity_used
                elif isinstance(variant, dict) and 'discount_quantity_used' in variant:
                    variant_dict["discount_quantity_used"] = variant['discount_quantity_used']
                
                processed_variants[variant_type].append(variant_dict)
        
        return JSONResponse(
            content={
                "success": True,
                "product_id": product_id,
                "product_name": product.name,
                "variants": processed_variants,
                "variant_types": list(product.variants.keys())
            }
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={
                "success": False,
                "error": f"Error fetching product variants: {str(e)}"
            },
            status_code=500
        )

@router.post("/{product_id}/variants/{variant_id}/discount")
async def set_variant_discount(
    product_id: str,
    variant_id: str,
    old_price: Optional[str] = Form(None),
    discount_price: Optional[str] = Form(None),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    quantity_limit: Optional[int] = Form(None),
    current_user: User = Depends(get_current_active_admin)
):
    """
    Set a discount on a specific product variant
    """
    try:
        print(f"Setting discount for product ID: {product_id}, variant ID: {variant_id}")
        print(f"Form data: old_price={old_price}, discount_price={discount_price}, start_date={start_date}, end_date={end_date}, quantity_limit={quantity_limit}")
        
        # Find the product
        product = await Product.find_one({"_id": product_id})
        
        # If not found by id, try _id (in case MongoDB is using _id instead)
        if not product:
            print(f"Product not found by id, trying _id...")
            try:
                from bson import ObjectId
                if ObjectId.is_valid(product_id):
                    product = await Product.find_one({"_id": ObjectId(product_id)})
                    print(f"Product found by _id: {product is not None}")
            except Exception as e:
                print(f"Error when searching by _id: {e}")
        
        if not product:
            print(f"Product not found: {product_id}")
            raise HTTPException(status_code=404, detail="Product not found")
            
        # Calculate discount percentage if both prices are provided
        discount_percentage = None
        if old_price and discount_price:
            original_price = float(old_price)
            new_price = float(discount_price)
            
            if new_price >= original_price:
                raise HTTPException(status_code=400, detail="Discount price must be less than original price")
                
            discount_percentage = round(100 - (new_price / original_price * 100), 2)
        
        print(f"Calculated discount percentage: {discount_percentage}%")
        
        # Process date parameters
        discount_start_date = None
        if start_date:
            try:
                discount_start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                # Ensure start date is not in the past
                now = datetime.now()
                if discount_start_date < now:
                    discount_start_date = now
            except ValueError as e:
                print(f"Error parsing start_date: {e}")
                discount_start_date = datetime.now()
        else:
            discount_start_date = datetime.now()
            
        discount_end_date = None
        if end_date:
            try:
                discount_end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                # Ensure end date is after start date
                if discount_end_date < discount_start_date:
                    discount_end_date = discount_start_date + timedelta(days=30)
            except ValueError as e:
                print(f"Error parsing end_date: {e}")
                discount_end_date = discount_start_date + timedelta(days=30)
        else:
            discount_end_date = discount_start_date + timedelta(days=30)
            
        print(f"Discount period: {discount_start_date} to {discount_end_date}")
        
        # Find the variant in the product
        found_variant = False
        for variant_type, variants in product.variants.items():
            for i, variant in enumerate(variants):
                variant_id_str = str(variant.id) if hasattr(variant, 'id') else None
                if variant_id_str == variant_id:
                    # Update variant discount info
                    print(f"Found variant {variant_id} in type {variant_type}")
                    product.variants[variant_type][i].discount_percentage = discount_percentage
                    product.variants[variant_type][i].discount_start_date = discount_start_date
                    product.variants[variant_type][i].discount_end_date = discount_end_date
                    
                    # Add quantity limit if provided
                    if quantity_limit is not None and quantity_limit > 0:
                        product.variants[variant_type][i].discount_quantity_limit = quantity_limit
                        product.variants[variant_type][i].discount_quantity_used = 0  # Initialize counter
                        print(f"Discount limited to {quantity_limit} items")
                    else:
                        # Remove quantity limit if it was previously set
                        if hasattr(product.variants[variant_type][i], 'discount_quantity_limit'):
                            delattr(product.variants[variant_type][i], 'discount_quantity_limit')
                        if hasattr(product.variants[variant_type][i], 'discount_quantity_used'):
                            delattr(product.variants[variant_type][i], 'discount_quantity_used')
                    
                    # Record this discount in the discount activity history
                    from app.models.product import DiscountActivity
                    
                    # Create a new discount activity record
                    discount_activity = DiscountActivity(
                        discount_percentage=discount_percentage,
                        start_date=discount_start_date,
                        end_date=discount_end_date,
                        quantity_limit=quantity_limit,
                        items_sold=0,
                        is_active=True
                    )
                    
                    # Mark any previous active discounts as inactive
                    if hasattr(product.variants[variant_type][i], 'discount_activity'):
                        for activity in product.variants[variant_type][i].discount_activity:
                            if hasattr(activity, 'is_active') and activity.is_active:
                                activity.is_active = False
                    else:
                        product.variants[variant_type][i].discount_activity = []
                    
                    # Add the new discount activity to the list
                    product.variants[variant_type][i].discount_activity.append(discount_activity)
                    print(f"Recorded discount activity: {discount_activity}")
                    
                    found_variant = True
                    variant_info = {
                        "type": variant_type,
                        "value": variant.value
                    }
                    break
            if found_variant:
                break
                
        if not found_variant:
            print(f"Variant not found: {variant_id}")
            # Show a list of available variants for debugging
            available_variants = []
            for variant_type, variants in product.variants.items():
                for variant in variants:
                    variant_id_str = str(variant.id) if hasattr(variant, 'id') else None
                    available_variants.append({
                        "type": variant_type,
                        "value": variant.value,
                        "id": variant_id_str
                    })
            print(f"Available variants: {available_variants}")
            raise HTTPException(status_code=404, detail="Variant not found")
            
        # Save the updated product
        print(f"Saving product with updated discount...")
        await product.save()
        print(f"Product saved successfully")
        
        # Create response data
        response_data = {
            "success": True,
            "message": f"Discount of {discount_percentage}% applied successfully to {variant_info['type']}: {variant_info['value']}",
            "product_id": product_id,
            "variant_id": variant_id,
            "discount_percentage": discount_percentage,
            "discount_start_date": discount_start_date.isoformat(),
            "discount_end_date": discount_end_date.isoformat(),
        }
        
        # Add quantity limit to response if applicable
        if quantity_limit is not None and quantity_limit > 0:
            response_data["quantity_limit"] = quantity_limit
            response_data["message"] += f" (Limited to {quantity_limit} items)"
            
        return JSONResponse(content=response_data)
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error in set_variant_discount: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Could not set variant discount: {str(e)}"
        )

@router.post("/{product_id}/variants/{variant_id}/remove-discount")
async def remove_variant_discount(
    product_id: str,
    variant_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Remove a discount from a specific product variant
    """
    try:
        print(f"Removing discount for product ID: {product_id}, variant ID: {variant_id}")
        
        # Find the product
        product = await Product.find_one({"_id": product_id})
        
        # If not found by id, try ObjectId (in case MongoDB is using ObjectId instead)
        if not product:
            print(f"Product not found by id, trying ObjectId...")
            try:
                from bson import ObjectId
                if ObjectId.is_valid(product_id):
                    product = await Product.find_one({"_id": ObjectId(product_id)})
                    print(f"Product found by ObjectId: {product is not None}")
            except Exception as e:
                print(f"Error when searching by ObjectId: {e}")
        
        if not product:
            print(f"Product not found: {product_id}")
            raise HTTPException(status_code=404, detail="Product not found")
            
        # Find the variant in the product
        found_variant = False
        for variant_type, variants in product.variants.items():
            for i, variant in enumerate(variants):
                variant_id_str = str(variant.id) if hasattr(variant, 'id') else None
                if variant_id_str == variant_id:
                    # Store variant info for response message
                    variant_info = {
                        "type": variant_type,
                        "value": variant.value,
                        "original_discount": variant.discount_percentage
                    }
                    
                    # Remove discount info
                    print(f"Found variant {variant_id} in type {variant_type}, removing discount")
                    product.variants[variant_type][i].discount_percentage = None
                    product.variants[variant_type][i].discount_start_date = None
                    product.variants[variant_type][i].discount_end_date = None
                    
                    # Also reset quantity limit and usage
                    product.variants[variant_type][i].discount_quantity_limit = None
                    product.variants[variant_type][i].discount_quantity_used = None
                    print(f"Reset discount quantity limits and usage to null")
                    
                    # Mark all active discount activities as inactive
                    if hasattr(product.variants[variant_type][i], 'discount_activity'):
                        for activity in product.variants[variant_type][i].discount_activity:
                            if hasattr(activity, 'is_active') and activity.is_active:
                                activity.is_active = False
                                print(f"Marked discount activity {activity.id} as inactive")
                    
                    found_variant = True
                    break
            if found_variant:
                break
                
        if not found_variant:
            print(f"Variant not found: {variant_id}")
            raise HTTPException(status_code=404, detail="Variant not found")
            
        # Save the updated product
        print(f"Saving product with removed discount...")
        await product.save()
        print(f"Product saved successfully")
        
        return JSONResponse(
            content={
                "success": True,
                "message": f"Discount removed successfully from {variant_info['type']}: {variant_info['value']}",
                "product_id": product_id,
                "variant_id": variant_id,
                "removed_discount": variant_info['original_discount']
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error in remove_variant_discount: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Could not remove variant discount: {str(e)}"
        )

@router.get("/{product_id}/debug")
async def debug_product(
    product_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Debug endpoint to inspect a product by ID
    """
    try:
        print(f"Debugging product with ID: {product_id}")
        
        # Try finding by id first
        product = await Product.find_one({"id": product_id})
        
        # If not found, try by _id
        if not product:
            print(f"Product not found by id, trying _id...")
            try:
                from bson import ObjectId
                if ObjectId.is_valid(product_id):
                    product = await Product.find_one({"_id": ObjectId(product_id)})
                    print(f"Product found by _id: {product is not None}")
            except Exception as e:
                print(f"Error when searching by _id: {e}")
        
        if not product:
            # Try to find a few products to compare their structure
            sample_products = []
            async for p in Product.find().limit(2):
                sample_products.append({
                    "id": p.id,
                    "_id": str(p._id) if hasattr(p, "_id") else None,
                    "name": p.name
                })
            
            return JSONResponse(
                content={
                    "success": False,
                    "message": f"Product not found with ID: {product_id}",
                    "sample_products": sample_products
                }
            )
        
        # Create a simplified representation of the product
        product_dict = {
            "id": product.id,
            "_id": str(product._id) if hasattr(product, "_id") else None,
            "name": product.name,
            "price": product.price,
            "discount_percentage": product.discount_percentage,
            "discount_start_date": str(product.discount_start_date) if product.discount_start_date else None,
            "discount_end_date": str(product.discount_end_date) if product.discount_end_date else None,
            "attributes": [
                {"key": attr.key, "value": attr.value} 
                for attr in product.attributes
            ] if product.attributes else [],
            "has_variants": bool(product.variants)
        }
        
        # Add variant summaries
        if product.variants:
            product_dict["variant_types"] = list(product.variants.keys())
            product_dict["variant_count"] = sum(len(variants) for variants in product.variants.values())
            
            # Add first few variants for each type as examples
            variant_examples = {}
            for variant_type, variants in product.variants.items():
                variant_examples[variant_type] = []
                for i, variant in enumerate(variants[:3]):  # Show up to 3 variants per type
                    variant_id = getattr(variant, "id", None)
                    variant_id_str = str(variant_id) if variant_id else None
                    variant_examples[variant_type].append({
                        "id": variant_id_str,
                        "value": getattr(variant, "value", None),
                        "price": getattr(variant, "price", None),
                        "discount_percentage": getattr(variant, "discount_percentage", None),
                        "discount_start_date": str(getattr(variant, "discount_start_date", None)) if getattr(variant, "discount_start_date", None) else None,
                        "discount_end_date": str(getattr(variant, "discount_end_date", None)) if getattr(variant, "discount_end_date", None) else None,
                    })
            product_dict["variant_examples"] = variant_examples
            
        return JSONResponse(
            content={
                "success": True,
                "product": product_dict
            }
        )
    except Exception as e:
        print(f"Error in debug_product: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={
                "success": False,
                "error": str(e)
            },
            status_code=500
        )

@router.get("/debug-all")
async def debug_all_products(
    current_user: User = Depends(get_current_active_admin)
):
    """
    Debug endpoint to show raw product IDs from the database
    """
    try:
        # List all products with their IDs
        products_data = []
        async for p in Product.find().limit(10):
            try:
                p_dict = {
                    "id": p.id,
                    "id_type": type(p.id).__name__,
                    "_id": str(p._id) if hasattr(p, "_id") else None,
                    "_id_type": type(p._id).__name__ if hasattr(p, "_id") else None,
                    "name": p.name,
                    "has_variants": bool(p.variants) if hasattr(p, "variants") else False
                }
                
                # Add variant details if exists
                if p_dict["has_variants"]:
                    p_dict["variant_types"] = list(p.variants.keys())
                    p_dict["variant_count"] = sum(len(variants) for variants in p.variants.values())
                    
                    # Add first variant as example
                    for variant_type, variants in p.variants.items():
                        if variants:
                            example_variant = variants[0]
                            p_dict["example_variant"] = {
                                "type": variant_type,
                                "id": getattr(example_variant, "id", None) or "unknown",
                                "id_type": type(getattr(example_variant, "id", None)).__name__,
                                "value": getattr(example_variant, "value", None) or "unknown",
                                "price": getattr(example_variant, "price", None)
                            }
                            break
                
                products_data.append(p_dict)
            except Exception as e:
                products_data.append({
                    "error": str(e),
                    "name": getattr(p, "name", "unknown")
                })
        
        # Test specific ID lookup
        specific_id = "66848ab7-c7f8-4d29-8d84-a51ec089cd38"
        
        # 1. Try direct lookup by id
        direct_product = await Product.find_one({"id": specific_id})
        
        # 2. Try with different formats/types
        from bson import ObjectId
        
        # Try with ObjectId
        obj_id_result = None
        if ObjectId.is_valid(specific_id):
            obj_id_product = await Product.find_one({"_id": ObjectId(specific_id)})
            if obj_id_product:
                obj_id_result = {
                    "id": obj_id_product.id,
                    "name": obj_id_product.name
                }
                
        # Try with UUID
        import uuid
        uuid_result = None
        try:
            uuid_obj = uuid.UUID(specific_id)
            uuid_product = await Product.find_one({"id": str(uuid_obj)})
            if uuid_product:
                uuid_result = {
                    "id": uuid_product.id,
                    "name": uuid_product.name
                }
        except:
            pass
        
        # Try raw aggregation
        from app.database import get_db
        db = await get_db()
        collection = db.products
        
        raw_products = []
        async for doc in collection.find({"id": specific_id}).limit(1):
            raw_products.append({k: str(v) for k, v in doc.items()})
            
        debug_info = {
            "specific_id_tested": specific_id,
            "direct_lookup_found": direct_product is not None,
            "direct_lookup_result": {
                "id": direct_product.id,
                "name": direct_product.name
            } if direct_product else None,
            "object_id_lookup": obj_id_result,
            "uuid_lookup": uuid_result,
            "raw_db_query": raw_products
        }
            
        return JSONResponse(
            content={
                "success": True,
                "products": products_data,
                "debug_info": debug_info
            }
        )
    except Exception as e:
        print(f"Error in debug_all_products: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={
                "success": False,
                "error": str(e)
            },
            status_code=500
        )

@router.get("/{product_id}/discount-history")
async def get_discount_history(
    product_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Get discount activity history for a product and its variants
    """
    try:
        print(f"Getting discount history for product ID: {product_id}")
        
        # Find the product
        product = await Product.find_one({"_id": product_id})
        
        # If not found by id, try ObjectId (in case MongoDB is using ObjectId instead)
        if not product:
            print(f"Product not found by id, trying ObjectId...")
            try:
                from bson import ObjectId
                if ObjectId.is_valid(product_id):
                    product = await Product.find_one({"_id": ObjectId(product_id)})
                    print(f"Product found by ObjectId: {product is not None}")
            except Exception as e:
                print(f"Error when searching by ObjectId: {e}")
        
        if not product:
            print(f"Product not found: {product_id}")
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Build discount history response
        discount_history = {
            "product_id": product_id,
            "product_name": product.name,
            "variants": {}
        }
        
        # Loop through variants to collect discount activity
        total_variants = 0
        total_discounts = 0
        total_items_sold = 0
        
        for variant_type, variants in product.variants.items():
            discount_history["variants"][variant_type] = []
            
            for variant in variants:
                total_variants += 1
                variant_history = {
                    "id": str(variant.id) if hasattr(variant, 'id') else "unknown",
                    "value": variant.value if hasattr(variant, 'value') else "unknown",
                    "price": variant.price if hasattr(variant, 'price') else 0,
                    "current_discount": variant.discount_percentage if hasattr(variant, 'discount_percentage') else None,
                    "discount_activity": []
                }
                
                # Add discount activity if available
                if hasattr(variant, 'discount_activity') and variant.discount_activity:
                    for activity in variant.discount_activity:
                        total_discounts += 1
                        total_items_sold += activity.items_sold if hasattr(activity, 'items_sold') else 0
                        
                        activity_dict = {
                            "id": str(activity.id) if hasattr(activity, 'id') else "unknown",
                            "discount_percentage": activity.discount_percentage if hasattr(activity, 'discount_percentage') else 0,
                            "start_date": activity.start_date.isoformat() if hasattr(activity, 'start_date') and activity.start_date else None,
                            "end_date": activity.end_date.isoformat() if hasattr(activity, 'end_date') and activity.end_date else None,
                            "quantity_limit": activity.quantity_limit if hasattr(activity, 'quantity_limit') else None,
                            "items_sold": activity.items_sold if hasattr(activity, 'items_sold') else 0,
                            "created_at": activity.created_at.isoformat() if hasattr(activity, 'created_at') and activity.created_at else None,
                            "is_active": activity.is_active if hasattr(activity, 'is_active') else False
                        }
                        
                        variant_history["discount_activity"].append(activity_dict)
                
                discount_history["variants"][variant_type].append(variant_history)
        
        # Add summary statistics
        discount_history["summary"] = {
            "total_variants": total_variants,
            "total_discounts_applied": total_discounts,
            "total_items_sold_with_discount": total_items_sold
        }
        
        return JSONResponse(
            content={
                "success": True,
                "discount_history": discount_history
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error in get_discount_history: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Could not get discount history: {str(e)}"
        )

@router.delete("/{product_id}/images")
async def delete_product_image(
    product_id: str,
    image_url: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Delete a single product image
    """
    try:
        # Find the product
        product = await Product.find_one({"id": product_id})
        if not product:
            product = await Product.find_one({"_id": product_id})
            
        if not product:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Product not found"}
            )
        
        # Remove image URL from product's image_urls list
        if image_url in product.image_urls:
            product.image_urls.remove(image_url)
            
            # Delete the image from storage
            deleted = delete_image(image_url)
            
            # Save the product with updated image list
            await product.save()
            
            if deleted:
                return JSONResponse(
                    status_code=200,
                    content={"success": True, "message": "Image deleted successfully"}
                )
            else:
                # The image was removed from the product but failed to delete from storage
                return JSONResponse(
                    status_code=200,
                    content={
                        "success": True, 
                        "message": "Image removed from product but failed to delete from storage"
                    }
                )
        else:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Image not found in product"}
            )
            
    except Exception as e:
        print(f"Error deleting product image: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Failed to delete image: {str(e)}"}
        )

@router.post("/{product_id}/images")
async def add_product_image(
    product_id: str,
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_active_admin)
):
    """
    Add a single image to a product
    """
    try:
        # Find the product
        product = await Product.find_one({"id": product_id})
        if not product:
            product = await Product.find_one({"_id": product_id})
            
        if not product:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Product not found"}
            )
        
        # Validate and upload the image
        if not image or not image.filename:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "No image provided"}
            )
            
        # Upload the image
        image_url = await validate_and_optimize_product_image(image)
        
        if not image_url:
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "Failed to upload image"}
            )
        
        # Add the image URL to the product's image_urls list
        if not hasattr(product, 'image_urls') or product.image_urls is None:
            product.image_urls = []
            
        product.image_urls.append(image_url)
        
        # Save the product with the new image
        await product.save()
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True, 
                "message": "Image added successfully",
                "image_url": image_url
            }
        )
            
    except Exception as e:
        print(f"Error adding product image: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Failed to add image: {str(e)}"}
        ) 