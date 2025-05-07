from fastapi import APIRouter, Request, Depends, HTTPException, status, Body
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timedelta
from app.database import get_db
from app.models.user import User, UserRole
from app.auth.jwt import get_current_user, get_current_active_admin, get_token_from_cookie
from app.admin.dashboard import templates, router
from app.utils.json import to_serializable_dict
from enum import Enum
import logging
from uuid import uuid4
from bson import ObjectId
import json
import traceback

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
        # Get products (assuming you have a Product model defined with Beanie)
        from app.models.product import Product

        products = []
        try:
            products = await Product.find_all().to_list()
        except Exception as e:
            print(f"Error fetching products: {str(e)}")

        # Convert products to serializable dict with datetime handling
        serialized_products = []
        for product in products:
            try:
                serialized_products.append(to_serializable_dict(product))
            except Exception as e:
                print(f"Error serializing product: {str(e)}")

        # Get pending orders count
        from app.models.order import Order

        pending_orders = 0
        try:
            pending_orders = await Order.find(
                {"status": {"$in": [OrderStatus.PENDING.value, OrderStatus.PROCESSING.value, OrderStatus.DELIVERING.value]}}
            ).count()
        except Exception as e:
            print(f"Error counting pending orders: {str(e)}")

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
        try:
            daily_sales_result = await Order.aggregate(daily_sales_pipeline).to_list()
            if daily_sales_result and len(daily_sales_result) > 0 and "total" in daily_sales_result[0]:
                daily_sales = daily_sales_result[0]["total"]
        except Exception as e:
            print(f"Error calculating daily sales: {str(e)}")

        # Get total users count
        total_users = 0
        try:
            total_users = await User.find_all().count()
        except Exception as e:
            print(f"Error counting users: {str(e)}")

        # Get recent orders (last 5)
        recent_orders = []
        try:
            recent_orders = await Order.find_all().sort([("created_at", -1)]).limit(5).to_list()

            # For each order, fetch the associated user
            for order in recent_orders:
                if hasattr(order, "user_id") and order.user_id:
                    try:
                        user = await User.find_one({"id": order.user_id})
                        if user:
                            # Store the user object
                            order.user = user
                    except Exception as e:
                        print(f"Error fetching user for order: {str(e)}")
        except Exception as e:
            print(f"Error fetching recent orders: {str(e)}")

        # Convert recent orders to serializable format
        serialized_orders = []
        for order in recent_orders:
            try:
                # Handle guest orders
                if not hasattr(order, "user") or not order.user:
                    # Check if we have guest data
                    if hasattr(order, "guest_data") and order.guest_data:
                        guest_name = order.guest_data.get("name", "Guest")
                        guest_phone = order.guest_data.get("phone", "")
                        guest_email = order.guest_data.get("email", "")
                        order.user = {
                            "username": guest_name,
                            "phone_number": guest_phone,
                            "email": guest_email
                        }
                    else:
                        order.user = {"username": "Guest"}

                # Get the serialized order
                serialized_order = to_serializable_dict(order)

                # Add the formatted properties
                if hasattr(order, 'created_at_formatted'):
                    serialized_order['created_at_formatted'] = order.created_at_formatted
                if hasattr(order, 'created_at_time'):
                    serialized_order['created_at_time'] = order.created_at_time
                if hasattr(order, 'formatted_amount'):
                    serialized_order['formatted_amount'] = order.formatted_amount

                serialized_orders.append(serialized_order)
            except Exception as e:
                print(f"Error serializing order: {str(e)}")

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

        # Safely serialize the current user
        serialized_user = None
        try:
            serialized_user = to_serializable_dict(current_user)
        except Exception as e:
            print(f"Error serializing current user: {str(e)}")
            serialized_user = {"username": current_user.username, "id": current_user.id}

        return templates.TemplateResponse(
            "dashboard/index.html",
            {
                "request": request,
                "products": serialized_products,
                "user": serialized_user,
                "pending_orders": pending_orders,
                "daily_sales": "{:.2f}".format(daily_sales),
                "total_users": total_users,
                "recent_orders": serialized_orders
            }
        )
    except Exception as e:
        # Return a basic error page if templates aren't working
        error_details = f"{type(e).__name__}: {str(e)}"
        return HTMLResponse(
            content=f"""
            <html>
                <head><title>Admin Dashboard Error</title></head>
                <body>
                    <h1>Error Loading Admin Dashboard</h1>
                    <p>Error: {error_details}</p>
                    <pre>{traceback.format_exc()}</pre>
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

        # Convert products to serializable dict with datetime handling
        serialized_products = [to_serializable_dict(product) for product in products]

        return JSONResponse(content=serialized_products)
    except Exception as e:
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

        discount_percentage = round(100 - (discount_price / original_price * 100), 2)

        # Find the product
        from app.models.product import Product
        product = await Product.find_one({"id": product_id})
        if not product:
            return JSONResponse(
                status_code=404,
                content={"detail": "Product not found"}
            )

        # Update product with discount
        product.old_price = int(original_price)
        product.discount_percentage = discount_percentage
        product.discount_start_date = datetime.now()
        product.discount_end_date = datetime.now() + timedelta(days=30)  # Default to 30 days

        # Save the updated product
        await product.save()

        # Convert to serializable format for response
        response_data = {
            "success": True,
            "message": f"Discount of {discount_percentage}% applied successfully",
            "product_id": product_id,
            "discount_percentage": discount_percentage,
            "new_price": discount_price,
            "discount_start_date": product.discount_start_date.isoformat(),
            "discount_end_date": product.discount_end_date.isoformat()
        }

        return JSONResponse(content=response_data)
    except Exception as e:
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

        discount_percentage = round(100 - (discount_price / original_price * 100), 2)

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

        # Update variant with discount info
        target_variant.discount_percentage = discount_percentage
        target_variant.discount_start_date = datetime.now()
        target_variant.discount_end_date = datetime.now() + timedelta(days=30)  # Default to 30 days

        # Save the updated product
        await target_product.save()

        # Convert dates to ISO format for response
        response_data = {
            "success": True,
            "message": f"Discount of {discount_percentage}% applied successfully to {variant_type}: {target_variant.value}",
            "product_id": target_product.id,
            "variant_id": variant_id,
            "discount_percentage": discount_percentage,
            "new_price": discount_price,
            "discount_start_date": target_variant.discount_start_date.isoformat(),
            "discount_end_date": target_variant.discount_end_date.isoformat()
        }

        return JSONResponse(content=response_data)
    except Exception as e:
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

    # Convert form_data to serializable format
    response_data = {
        "success": True,
        "message": "Debug information received",
        "form_data": form_dict,
        "body_data": data,
        "headers": dict(request.headers),
        "method": request.method
    }

    return JSONResponse(content=response_data)

@router.post("/api/admin/debug/form")
async def debug_form(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """Debugging endpoint for form submission"""
    form_data = await request.form()
    form_dict = {key: form_data[key] for key in form_data}

    # Convert form_data to serializable format
    response_data = {
        "success": True,
        "message": "Form data received",
        "form_data": form_dict,
        "headers": dict(request.headers),
        "method": request.method
    }

    return JSONResponse(content=response_data)

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

        # Convert product to serializable dict
        product_dict = to_serializable_dict(product)

        # Return a detailed response
        return JSONResponse(content=product_dict)
    except Exception as e:
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
    """API endpoint to debug a product's variants"""
    try:
        # Find the product
        from app.models.product import Product
        product = await Product.find_one({"id": product_id})
        if not product:
            return JSONResponse(
                status_code=404,
                content={"detail": "Product not found"}
            )

        # Try to get variants
        variants_info = {}
        if hasattr(product, 'variants') and product.variants:
            for vtype, variants in product.variants.items():
                variants_info[vtype] = []
                for i, variant in enumerate(variants):
                    variant_data = {
                        "index": i,
                        "id": variant.get("id", f"unknown_{i}"),
                        "value": variant.get("value", "Unknown"),
                        "price": variant.get("price", 0)
                    }
                    variants_info[vtype].append(variant_data)
        else:
            variants_info = {"message": "Product has no variants"}

        return JSONResponse(content=variants_info)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"detail": f"Failed to get variant information: {str(e)}"}
        )

@router.get("/variant-test", response_class=HTMLResponse)
async def variant_test_page(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """Page to test variant loading functionality"""
    return templates.TemplateResponse(
        "dashboard/variant-test.html",
        {"request": request, "user": to_serializable_dict(current_user)}
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
            # Convert _id to string for serialization
            doc1["_id"] = str(doc1["_id"])
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
                # Convert _id to string for serialization
                doc2["_id"] = str(doc2["_id"])
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
            # Convert _id to string for serialization
            doc3["_id"] = str(doc3["_id"])
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

        # Store original for comparison (convert ObjectId to string)
        original_doc = dict(product_doc)
        original_doc["_id"] = str(original_doc["_id"])

        results["original"] = {
            "id": original_doc.get("id"),
            "_id": original_doc.get("_id"),
            "name": original_doc.get("name"),
            "has_variants": "variants" in original_doc and bool(original_doc["variants"])
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

                    # Convert any datetime objects to strings
                    for key, value in fixed_variant.items():
                        if isinstance(value, datetime):
                            fixed_variant[key] = value.isoformat()
                            results["actions"].append(f"Converted datetime field {key} to ISO format string")

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
            # Convert _id to string for JSON serialization
            updated_doc["_id"] = str(updated_doc["_id"])

            results["fixed"] = {
                "id": updated_doc.get("id"),
                "_id": updated_doc.get("_id"),
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
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

@router.get("/api/admin/stats/monthly-sales")
async def get_monthly_sales(
    year: int = None,
    request: Request = None,
    current_user: User = Depends(get_current_active_admin)
):
    """Get monthly sales data for the current year"""
    try:
        from app.models.order import Order

        # Default to current year if not specified
        if not year:
            year = datetime.now().year

        # Create date ranges for each month
        monthly_data = []
        for month in range(1, 13):
            month_start = datetime(year, month, 1)
            # Calculate end of month (start of next month - 1 day)
            if month == 12:
                month_end = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = datetime(year, month + 1, 1) - timedelta(days=1)

            # Set times to start and end of day
            month_start = datetime.combine(month_start, datetime.min.time())
            month_end = datetime.combine(month_end, datetime.max.time())

            # Query completed orders for this month
            pipeline = [
                {
                    "$match": {
                        "created_at": {"$gte": month_start, "$lte": month_end},
                        "status": {"$in": [OrderStatus.COMPLETED.value, OrderStatus.DELIVERING.value]}
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total": {"$sum": "$total_amount"},
                        "count": {"$sum": 1}
                    }
                }
            ]

            monthly_result = await Order.aggregate(pipeline).to_list()

            # Handle case where there are no orders for the month
            total = 0
            count = 0
            if monthly_result and len(monthly_result) > 0:
                result_item = monthly_result[0]
                if "total" in result_item:
                    total = result_item["total"]
                if "count" in result_item:
                    count = result_item["count"]

            # Add month data to results
            monthly_data.append({
                "month": month,
                "month_name": datetime(2000, month, 1).strftime("%b"),  # Jan, Feb, etc.
                "sales": total,
                "orders": count
            })

        return JSONResponse(content=monthly_data)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"detail": f"Failed to get monthly sales: {str(e)}"}
        )