from fastapi import APIRouter, Request, Depends, HTTPException, status, Body
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timedelta
from app.database import get_db
from app.models.user import User, UserRole
from app.auth.jwt import get_current_user, get_current_active_admin, get_token_from_cookie
from app.admin.dashboard import templates, router
from enum import Enum
import logging
from uuid import uuid4
from bson import ObjectId
import json

# Configure logging
logger = logging.getLogger(__name__)

# Define OrderStatus if not already defined elsewhere
class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

@router.get("/", response_class=HTMLResponse)
async def admin_home(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    try:
        # Log authentication information for debugging
        token = request.cookies.get("access_token")
        logger.info(f"Admin access attempt - Token present: {bool(token)}")
        
        if token:
            token_value = token.replace("Bearer ", "") if token.startswith("Bearer ") else token
            logger.info(f"Token value (first 10 chars): {token_value[:10]}...")
        
        logger.info(f"Current user: {current_user.username} (role: {current_user.role})")
        
        # Get products (assuming you have a Product model defined with Beanie)
        from app.models.product import Product
        products = await Product.find_all().to_list()
        
        # Convert products to dict to ensure proper serialization of variants
        serialized_products = []
        for product in products:
            # Convert the Product object to a dictionary
            try:
                product_dict = dict(product)
            except TypeError:
                # If direct dict conversion fails, try to get the model_dump method
                product_dict = product.model_dump() if hasattr(product, 'model_dump') else product.dict()
            
            # Ensure variants are properly serialized
            if product_dict.get('variants'):
                serialized_variants = {}
                for variant_type, variant_list in product_dict['variants'].items():
                    # Convert each variant value to a dictionary if it's not already one
                    serialized_variants[variant_type] = [
                        dict(v) if not isinstance(v, dict) else v 
                        for v in variant_list
                    ]
                product_dict['variants'] = serialized_variants
            serialized_products.append(product_dict)
            
        logger.info(f"Found {len(serialized_products)} products")
        
        # Get pending orders count
        from app.models.order import Order
        pending_orders = await Order.find(
            {"status": {"$in": [OrderStatus.PENDING.value, OrderStatus.PROCESSING.value, OrderStatus.DELIVERING.value]}}
        ).count()
        logger.info(f"Found {pending_orders} pending orders")
        
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
        
        daily_sales_result = await Order.aggregate(daily_sales_pipeline).to_list()
        daily_sales = daily_sales_result[0]["total"] if daily_sales_result else 0
        logger.info(f"Daily sales: {daily_sales}")
        
        # Get total users count
        total_users = await User.find_all().count()
        logger.info(f"Total users: {total_users}")
        
        # Get recent orders (last 5)
        recent_orders = await Order.find_all().sort([("created_at", -1)]).limit(5).to_list()
        logger.info(f"Found {len(recent_orders)} recent orders")
        
        # For each order, fetch the associated user
        for order in recent_orders:
            if hasattr(order, "user_id"):
                order.user = await User.find_one({"id": order.user_id})
        
        # For now, return a simple success message if templates aren't set up yet
        if not hasattr(templates, "TemplateResponse"):
            return HTMLResponse(content=f"""
            <html>
                <head><title>Admin Dashboard</title></head>
                <body>
                    <h1>Admin Dashboard</h1>
                    <p>Welcome, {current_user.username}!</p>
                    <p>Products: {len(serialized_products)}</p>
                    <p>Pending Orders: {pending_orders}</p>
                    <p>Daily Sales: ${daily_sales:.2f}</p>
                    <p>Total Users: {total_users}</p>
                </body>
            </html>
            """)
        
        return templates.TemplateResponse(
            "dashboard/index.html",
            {
                "request": request,
                "products": serialized_products,
                "user": current_user,
                "pending_orders": pending_orders,
                "daily_sales": "{:.2f}".format(daily_sales),
                "total_users": total_users,
                "recent_orders": recent_orders
            }
        )
    except Exception as e:
        logger.error(f"Admin dashboard error: {e}")
        print(f"Admin dashboard error: {e}")
        
        # Return a basic error page if templates aren't working
        return HTMLResponse(
            content=f"""
            <html>
                <head><title>Admin Dashboard Error</title></head>
                <body>
                    <h1>Error Loading Admin Dashboard</h1>
                    <p>Error: {str(e)}</p>
                    <p><a href="/auth/login">Return to login</a></p>
                </body>
            </html>
            """,
            status_code=500
        )

@router.get("/api/admin/products")
async def get_admin_products(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """API endpoint to fetch products for the admin dashboard"""
    try:
        # Get products
        from app.models.product import Product
        products = await Product.find_all().to_list()
        
        # Convert products to dict to ensure proper serialization of variants
        serialized_products = []
        for product in products:
            # Convert the Product object to a dictionary
            try:
                product_dict = dict(product)
            except TypeError:
                # If direct dict conversion fails, try to get the model_dump method
                product_dict = product.model_dump() if hasattr(product, 'model_dump') else product.dict()
            
            # Ensure variants are properly serialized
            if product_dict.get('variants'):
                serialized_variants = {}
                for variant_type, variant_list in product_dict['variants'].items():
                    # Convert each variant value to a dictionary if it's not already one
                    serialized_variants[variant_type] = [
                        dict(v) if not isinstance(v, dict) else v 
                        for v in variant_list
                    ]
                product_dict['variants'] = serialized_variants
            serialized_products.append(product_dict)
            
        return JSONResponse(content=serialized_products)
    except Exception as e:
        logger.error(f"Error fetching admin products: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"Failed to fetch products: {str(e)}"}
        )

@router.post("/api/admin/products/{product_id}/discount")
async def set_product_discount(
    product_id: str,
    request: Request,
    data: dict = Body(...),
    current_user: User = Depends(get_current_active_admin)
):
    """API endpoint to set a discount on a product"""
    try:
        # Get data from request
        original_price = data.get("original_price")
        discount_price = data.get("discount_price")
        
        if not original_price or not discount_price:
            return JSONResponse(
                status_code=400,
                content={"detail": "Original price and discount price are required"}
            )
            
        # Calculate discount percentage
        original_price = float(original_price)
        discount_price = float(discount_price)
        
        if discount_price >= original_price:
            return JSONResponse(
                status_code=400,
                content={"detail": "Discount price must be less than original price"}
            )
            
        discount_percentage = round(100 - (discount_price / original_price * 100))
        
        # Find the product
        from app.models.product import Product
        product = await Product.find_one({"id": product_id})
        if not product:
            return JSONResponse(
                status_code=404,
                content={"detail": "Product not found"}
            )
        
        logger.info(f"Setting discount for product {product_id}: {discount_percentage}%")
        
        # Update product with discount
        product.old_price = int(original_price)
        product.discount_percentage = discount_percentage
        product.discount_start_date = datetime.now()
        product.discount_end_date = datetime.now() + timedelta(days=30)  # Default to 30 days
        
        # Save the updated product
        await product.save()
        
        return JSONResponse(
            content={
                "success": True,
                "message": f"Discount of {discount_percentage}% applied successfully",
                "product_id": product_id,
                "discount_percentage": discount_percentage,
                "new_price": discount_price
            }
        )
    except Exception as e:
        logger.error(f"Error setting product discount: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"Failed to set discount: {str(e)}"}
        )

@router.post("/api/admin/variants/{variant_id}/discount")
async def set_variant_discount(
    variant_id: str,
    request: Request,
    data: dict = Body(...),
    current_user: User = Depends(get_current_active_admin)
):
    """API endpoint to set a discount on a product variant"""
    try:
        # Get data from request
        original_price = data.get("original_price")
        discount_price = data.get("discount_price")
        
        if not original_price or not discount_price:
            return JSONResponse(
                status_code=400,
                content={"detail": "Original price and discount price are required"}
            )
            
        # Calculate discount percentage
        original_price = float(original_price)
        discount_price = float(discount_price)
        
        if discount_price >= original_price:
            return JSONResponse(
                status_code=400,
                content={"detail": "Discount price must be less than original price"}
            )
            
        discount_percentage = round(100 - (discount_price / original_price * 100))
        
        # Find product with the variant
        from app.models.product import Product
        
        # We need to search across all products to find the one containing this variant
        products = await Product.find_all().to_list()
        target_product = None
        target_variant = None
        variant_type = None
        
        # Find the product and variant
        for product in products:
            if not hasattr(product, 'variants') or not product.variants:
                continue
                
            # Search through each variant type and its values
            for v_type, variants in product.variants.items():
                for variant in variants:
                    # Check if this is the variant we're looking for
                    if variant.id == variant_id or str(variant.id) == variant_id:
                        target_product = product
                        target_variant = variant
                        variant_type = v_type
                        break
                if target_variant:
                    break
            if target_variant:
                break
        
        if not target_product or not target_variant:
            return JSONResponse(
                status_code=404,
                content={"detail": "Variant not found"}
            )
        
        logger.info(f"Setting discount for variant {variant_id} of product {target_product.id}: {discount_percentage}%")
        
        # Update variant with discount info
        target_variant.discount_percentage = discount_percentage
        target_variant.discount_start_date = datetime.now()
        target_variant.discount_end_date = datetime.now() + timedelta(days=30)  # Default to 30 days
        
        # Save the updated product
        await target_product.save()
        
        return JSONResponse(
            content={
                "success": True,
                "message": f"Discount of {discount_percentage}% applied successfully to {variant_type}: {target_variant.value}",
                "product_id": target_product.id,
                "variant_id": variant_id,
                "discount_percentage": discount_percentage,
                "new_price": discount_price
            }
        )
    except Exception as e:
        logger.error(f"Error setting variant discount: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"Failed to set discount: {str(e)}"}
        )

@router.post("/api/admin/debug/discount")
async def debug_discount(
    request: Request,
    data: dict = Body(...),
    current_user: User = Depends(get_current_active_admin)
):
    """Debugging endpoint for discount requests"""
    form_data = await request.form()
    form_dict = {key: form_data[key] for key in form_data}
    
    return JSONResponse({
        "success": True,
        "message": "Debug information received",
        "form_data": form_dict,
        "body_data": data,
        "headers": dict(request.headers),
        "method": request.method
    })

@router.post("/api/admin/debug/form")
async def debug_form(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """Debugging endpoint for form submission"""
    form_data = await request.form()
    form_dict = {key: form_data[key] for key in form_data}
    
    return JSONResponse({
        "success": True,
        "message": "Form data received",
        "form_data": form_dict,
        "headers": dict(request.headers),
        "method": request.method
    })

@router.get("/api/admin/debug/product/{product_id}")
async def debug_product(
    product_id: str,
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """Debug endpoint to inspect a product and its variants"""
    try:
        from app.models.product import Product
        
        # Find the product
        product = await Product.find_one({"id": product_id})
        if not product:
            return JSONResponse(
                status_code=404,
                content={"detail": "Product not found"}
            )
        
        # Log details for debugging
        logger.info(f"Found product: {product.id} - {product.name}")
        
        # Try to get variants
        variants_info = {}
        
        if hasattr(product, 'variants') and product.variants:
            logger.info(f"Product has variants of types: {list(product.variants.keys())}")
            
            # Track variant details for each type
            for vtype, variants in product.variants.items():
                variants_info[vtype] = []
                for i, variant in enumerate(variants):
                    # Extract key information
                    variant_data = {
                        "index": i,
                        "id": getattr(variant, 'id', None),
                        "value": getattr(variant, 'value', None),
                        "price": getattr(variant, 'price', None),
                    }
                    variants_info[vtype].append(variant_data)
                    logger.info(f"Variant {i} of type {vtype}: {variant_data}")
        else:
            logger.info("Product has no variants")
        
        # Try to convert to dictionary
        try:
            product_dict = product.dict()
            logger.info("Successfully converted product to dict")
        except Exception as e:
            logger.error(f"Error converting product to dict: {e}")
            try:
                product_dict = product.model_dump() if hasattr(product, 'model_dump') else {}
                logger.info("Successfully converted product using model_dump")
            except Exception as e:
                logger.error(f"Error converting product using model_dump: {e}")
                product_dict = {"id": product.id, "name": product.name}
        
        # Return a detailed response
        return JSONResponse(
            content={
                "product_id": product.id,
                "product_name": product.name,
                "has_variants": bool(variants_info),
                "variant_types": list(variants_info.keys()) if variants_info else [],
                "variant_counts": {vtype: len(variants) for vtype, variants in variants_info.items()} if variants_info else {},
                "variants_info": variants_info,
                "raw_product": product_dict
            }
        )
    except Exception as e:
        logger.error(f"Error in debug_product: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"Error: {str(e)}"}
        )

@router.get("/api/admin/debug/product/{product_id}/variants")
async def debug_product_variants(
    product_id: str,
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """Debug endpoint to get product variants in different formats"""
    try:
        from app.models.product import Product
        
        # Find the product
        product = await Product.find_one({"id": product_id})
        if not product:
            return JSONResponse(
                status_code=404,
                content={"detail": "Product not found"}
            )
        
        # Log details for debugging
        logger.info(f"Debug variants for product: {product.id} - {product.name}")
        
        # Check if product has variants
        if not hasattr(product, 'variants') or not product.variants:
            return JSONResponse(
                content={
                    "message": "Product has no variants",
                    "product_id": product_id,
                    "product_name": product.name,
                    "variants": {}
                }
            )
        
        # Try to extract variants in different formats
        variants_by_type = {}  # Original structure
        variants_flat = []     # Flattened array
        
        for variant_type, variant_values in product.variants.items():
            variants_by_type[variant_type] = []
            
            for variant in variant_values:
                # Try to convert to dict using different methods
                try:
                    if hasattr(variant, 'dict'):
                        variant_dict = variant.dict()
                    elif hasattr(variant, 'model_dump'):
                        variant_dict = variant.model_dump()
                    else:
                        variant_dict = {k: v for k, v in variant.__dict__.items() if not k.startswith('_')}
                        
                    # Make sure id and value are present
                    variant_dict['id'] = getattr(variant, 'id', None)
                    variant_dict['value'] = getattr(variant, 'value', None)
                    variant_dict['price'] = getattr(variant, 'price', 0)
                    
                    # Add to both structures
                    variants_by_type[variant_type].append(variant_dict)
                    
                    # Add type to flat version
                    flat_variant = dict(variant_dict)
                    flat_variant['type'] = variant_type
                    variants_flat.append(flat_variant)
                    
                except Exception as e:
                    logger.error(f"Error serializing variant: {e}")
                    # Add a minimal version
                    minimal_variant = {
                        "id": getattr(variant, 'id', str(uuid4())),
                        "value": getattr(variant, 'value', "Unknown"),
                        "price": getattr(variant, 'price', 0),
                        "type": variant_type
                    }
                    variants_by_type[variant_type].append(minimal_variant)
                    variants_flat.append(minimal_variant)
        
        return JSONResponse(
            content={
                "message": "Variants debug information",
                "product_id": product_id,
                "product_name": product.name,
                "has_variants": True,
                "variant_types": list(variants_by_type.keys()),
                "variant_counts": {vtype: len(variants) for vtype, variants in variants_by_type.items()},
                "variants_by_type": variants_by_type,
                "variants_flat": variants_flat
            }
        )
    except Exception as e:
        logger.error(f"Error in debug_product_variants: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"Error: {str(e)}"}
        )

@router.get("/variant-test", response_class=HTMLResponse)
async def variant_test_page(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """Page to test variant loading functionality"""
    return templates.TemplateResponse(
        "dashboard/variant-test.html",
        {"request": request, "user": current_user}
    )

@router.get("/api/debug/find")
async def debug_find_product(
    id: str,
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """Debug endpoint for direct MongoDB find operation"""
    try:
        from app.database import get_db
        from bson import ObjectId
        import json
        
        db = await get_db()
        collection = db.products
        
        results = {
            "id_tested": id,
            "results": []
        }
        
        # Method 1: Direct id lookup
        doc1 = await collection.find_one({"id": id})
        if doc1:
            results["results"].append({
                "method": "Direct id lookup",
                "found": True,
                "id": doc1.get("id"),
                "name": doc1.get("name")
            })
        else:
            results["results"].append({
                "method": "Direct id lookup",
                "found": False
            })
            
        # Method 2: ObjectId lookup if valid
        if ObjectId.is_valid(id):
            doc2 = await collection.find_one({"_id": ObjectId(id)})
            if doc2:
                results["results"].append({
                    "method": "ObjectId lookup",
                    "found": True,
                    "id": doc2.get("id"),
                    "name": doc2.get("name")
                })
            else:
                results["results"].append({
                    "method": "ObjectId lookup",
                    "found": False
                })
                
        # Method 3: Case insensitive lookup
        doc3 = await collection.find_one({"id": {"$regex": f"^{id}$", "$options": "i"}})
        if doc3:
            results["results"].append({
                "method": "Case insensitive lookup",
                "found": True,
                "id": doc3.get("id"),
                "name": doc3.get("name")
            })
        else:
            results["results"].append({
                "method": "Case insensitive lookup",
                "found": False
            })
            
        # Method 4: Raw find with limit
        raw_docs = []
        async for doc in collection.find().limit(3):
            raw_docs.append({
                "id": doc.get("id"),
                "_id": str(doc.get("_id")),
                "name": doc.get("name")
            })
            
        results["sample_products"] = raw_docs
        
        return JSONResponse(content=results)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

@router.get("/api/debug/fix-product")
async def debug_fix_product(
    id: str,
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """Debug endpoint to fix product data in MongoDB directly"""
    try:
        from app.database import get_db
        from bson import ObjectId
        import json
        
        db = await get_db()
        collection = db.products
        
        results = {
            "id_tested": id,
            "original": None,
            "fixed": None,
            "actions": []
        }
        
        # Step 1: Find the product
        product_doc = None
        
        # Try by id
        product_doc = await collection.find_one({"id": id})
        lookup_method = "id"
        
        # If not found, try by _id if valid ObjectId
        if not product_doc and ObjectId.is_valid(id):
            product_doc = await collection.find_one({"_id": ObjectId(id)})
            lookup_method = "_id"
            
        if not product_doc:
            return JSONResponse(
                content={
                    "success": False,
                    "message": f"Product not found with ID: {id}"
                }
            )
        
        # Store original for comparison
        results["original"] = {
            "id": product_doc.get("id"),
            "_id": str(product_doc.get("_id")),
            "name": product_doc.get("name"),
            "has_variants": "variants" in product_doc and bool(product_doc["variants"])
        }
        
        # Step 2: Analyze variants and fix if needed
        fixed_doc = dict(product_doc)  # Make a copy to modify
        
        # Check for variants
        if "variants" in product_doc and product_doc["variants"]:
            results["actions"].append("Found variants to analyze")
            fixed_variants = {}
            
            # Process each variant type
            for variant_type, variants in product_doc["variants"].items():
                fixed_variants[variant_type] = []
                
                # Process each variant
                for variant in variants:
                    fixed_variant = dict(variant)  # Copy to modify
                    
                    # Ensure variant has an ID
                    if "id" not in fixed_variant or not fixed_variant["id"]:
                        from uuid import uuid4
                        fixed_variant["id"] = str(uuid4())
                        results["actions"].append(f"Added missing ID to variant: {variant_type} - {fixed_variant.get('value', 'unknown')}")
                    
                    # Ensure variant ID is string
                    if not isinstance(fixed_variant["id"], str):
                        fixed_variant["id"] = str(fixed_variant["id"])
                        results["actions"].append(f"Converted variant ID to string: {variant_type} - {fixed_variant.get('value', 'unknown')}")
                    
                    fixed_variants[variant_type].append(fixed_variant)
            
            # Replace variants with fixed version
            fixed_doc["variants"] = fixed_variants
            results["actions"].append("Processed all variants")
            
        # Step 3: Update the document if changes were made
        if results["original"] != fixed_doc:
            update_result = await collection.replace_one(
                {"_id": product_doc["_id"]}, 
                fixed_doc
            )
            
            results["update_result"] = {
                "matched_count": update_result.matched_count,
                "modified_count": update_result.modified_count,
                "acknowledged": update_result.acknowledged
            }
            
            results["actions"].append("Updated document in database")
        else:
            results["actions"].append("No changes needed")
        
        # Step 4: Verify the fix by retrieving the document again
        updated_doc = await collection.find_one({"_id": product_doc["_id"]})
        
        if updated_doc:
            results["fixed"] = {
                "id": updated_doc.get("id"),
                "_id": str(updated_doc.get("_id")),
                "name": updated_doc.get("name"),
                "has_variants": "variants" in updated_doc and bool(updated_doc["variants"])
            }
            
            # Add sample of fixed variants
            if "variants" in updated_doc and updated_doc["variants"]:
                variant_samples = {}
                for variant_type, variants in updated_doc["variants"].items():
                    if variants:
                        variant_samples[variant_type] = []
                        for variant in variants[:2]:  # Just show first 2 of each type
                            variant_samples[variant_type].append({
                                "id": variant.get("id"),
                                "value": variant.get("value"),
                                "price": variant.get("price")
                            })
                
                results["fixed"]["variant_samples"] = variant_samples
        
        return JSONResponse(content=results)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )