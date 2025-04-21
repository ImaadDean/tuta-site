from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.database import get_db
from app.models.order import Order, OrderCreate, OrderStatus, OrderItem, ShippingAddress, PaymentStatus
from app.models.user import User
from app.models.address import Address
from app.models.product import Product
from app.auth.jwt import get_current_user, get_current_user_optional
from app.client.checkout import router, templates
from app.utils.time import get_eat_time
import json
from uuid import uuid4
from datetime import datetime
import random
import string
import logging
from typing import Optional, List, Dict, Any, Union

# Set up logger
logger = logging.getLogger(__name__)

def generate_order_number() -> str:
    """Generate a unique 5-character order number."""
    # Use uppercase letters and numbers, excluding similar-looking characters
    chars = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'
    return ''.join(random.choices(chars, k=5))

async def create_unique_order_number(max_attempts: int = 10) -> Optional[str]:
    """
    Create a unique order number with retry logic.
    Returns None if unable to generate a unique number after max_attempts.
    """
    for _ in range(max_attempts):
        order_no = generate_order_number()
        # Check if order number exists
        existing = await Order.find_one({"order_no": order_no})
        if not existing:
            return order_no
    return None

@router.get("/checkout", response_class=HTMLResponse)
async def checkout_page(
    request: Request, 
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    # If user is logged in, load their addresses
    if current_user:
        user_with_addresses = await User.find_one({"id": str(current_user.id)})
        if user_with_addresses:
            user_with_addresses.addresses = await Address.find({"user_id": str(current_user.id)}).to_list()
    else:
        user_with_addresses = None
    
    return templates.TemplateResponse(
        "checkout/checkout.html", 
        {"request": request, "user": user_with_addresses}
    )

@router.post("/checkout")
async def process_checkout(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    form_data = await request.form()
    
    # Get form data
    shipping_address = {
        "name": form_data.get("name"),
        "address": form_data.get("address"),
        "city": form_data.get("city"),
        "country": form_data.get("country", "Uganda"),  # Default to Uganda if not provided
    }
    
    # Validate that required address fields are present
    required_fields = ["address", "city"]
    for field in required_fields:
        if not shipping_address.get(field):
            return JSONResponse(
                {"success": False, "error": f"Missing required field: {field}"},
                status_code=400
            )
    
    # Parse cart data
    cart_json = form_data.get("cart")
    if not cart_json:
        raise HTTPException(status_code=400, detail="Cart is empty")
    
    try:
        cart_items = json.loads(cart_json)
        print("Cart items:", cart_items)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid cart data")
    
    # Calculate total amount
    total_amount = sum(item["price"] * item["quantity"] for item in cart_items)
    
    # Get selected payment method
    payment_method = form_data.get("payment_method", "cash")
    
    # Create an address entry for this order
    address_id = None
    save_address = form_data.get("save_address") == "on"
    address_name = form_data.get("address_name")
    
    # If address_name is not provided, use a default name
    if not address_name:
        address_name = "Default Address" if save_address else "Order Address"
    
    # Make save_address always False for guest users
    if not current_user:
        save_address = False
    
    try:
        # Log the address data for debugging
        print(f"Creating address with data: {shipping_address}")
        
        # Ensure database is initialized
        from app.database import initialize_mongodb
        await initialize_mongodb()
        
        # Create a new address
        new_address = Address(
            id=str(uuid4()),
            # Only link to user if they want to save it and are logged in
            user_id=str(current_user.id) if save_address and current_user else None,
            name=address_name if save_address else "Order Address",
            address=shipping_address.get("address", ""),
            city=shipping_address.get("city", ""),
            country=shipping_address.get("country", "Uganda"),
            is_default=False
        )
        
        # If we're saving to the user's account, check if it should be default
        if save_address and current_user:
            existing_addresses = await Address.find({"user_id": str(current_user.id)}).to_list()
            
            if not existing_addresses:
                new_address.is_default = True
        
        # Log that we're about to save the address
        print(f"About to save address: {new_address.id}")
        await new_address.save()
        address_id = str(new_address.id)
        print(f"Address saved successfully with ID: {address_id}")
        
    except Exception as e:
        import traceback
        print(f"Error saving address: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return JSONResponse(
            {"success": False, "error": f"Error saving address: {str(e)}"},
            status_code=500
        )
    
    # Create the order directly
    max_retries = 3
    order_data = None
    
    for attempt in range(max_retries):
        try:
            # Get a unique order number
            order_no = await create_unique_order_number()
            if not order_no:
                raise HTTPException(
                    status_code=500,
                    detail="Unable to generate unique order number. Please try again."
                )
            
            # Get current time
            current_time = get_eat_time()
            
            # Create the order
            db_order = Order(
                id=str(uuid4()),
                order_no=order_no,
                user_id=str(current_user.id) if current_user else None,
                address_id=address_id,
                total_amount=total_amount,
                amount_paid=0,  # Default to 0 paid
                status=OrderStatus.PENDING.value,
                payment_status="pending",
                created_at=current_time.replace(tzinfo=None),
                updated_at=current_time.replace(tzinfo=None)
            )
            
            await db_order.save()
            
            # Add order items
            for item in cart_items:
                try:
                    # Check if product exists first
                    product = await Product.find_one({"id": item["id"]})
                    
                    # Only add item if product exists
                    if product:
                        db_item = OrderItem(
                            id=str(uuid4()),
                            order_id=str(db_order.id),
                            product_id=item["id"],
                            quantity=item["quantity"]
                        )
                        await db_item.save()
                        
                        # Increment view_count for the product
                        if not hasattr(product, 'view_count') or product.view_count is None:
                            product.view_count = 0
                        product.view_count += 1
                        
                        # Increment sales_count for the product
                        if not hasattr(product, 'sales_count') or product.sales_count is None:
                            product.sales_count = 0
                        product.sales_count += item["quantity"]
                        
                        await product.save()
                    else:
                        # Product doesn't exist, log the error
                        print(f"Product with ID {item['id']} not found, skipping item")
                except Exception as item_error:
                    print(f"Error adding order item: {item_error}")
                    # Continue with other items instead of failing the entire order
            
            # Clear cart from session
            request.session["cart"] = []
            
            # Prepare response data
            order_data = {
                "id": str(db_order.id),
                "order_no": order_no,
                "total_amount": total_amount
            }
            
            # Success - break out of retry loop
            break
            
        except Exception as e:
            print(f"Error creating order: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error creating order: {str(e)}"
            )
    
    # Check if request wants JSON response (for AJAX)
    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header:
        return JSONResponse(order_data)
    else:
        # For regular form submissions - though we're not using this path
        return RedirectResponse(url=f"/check/order/{order_data['id']}", status_code=303)

@router.post("/api/process-order")
async def api_process_order(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Process order via API endpoint, returning JSON response.
    This endpoint is designed for AJAX requests.
    Supports both authenticated users and guest checkout.
    """
    form_data = await request.form()
    
    # Get form data
    shipping_address = {
        "name": form_data.get("name"),
        "address": form_data.get("address"),
        "city": form_data.get("city"),
        "country": form_data.get("country", "Uganda"),  # Default to Uganda if not provided
    }
    
    # Validate that required address fields are present
    required_fields = ["address", "city"]
    for field in required_fields:
        if not shipping_address.get(field):
            return JSONResponse(
                {"success": False, "error": f"Missing required field: {field}"},
                status_code=400
            )
    
    # Get customer info for guest users
    customer_name = form_data.get("name", "")
    customer_email = form_data.get("email", "")
    customer_phone = form_data.get("phone", "")
    
    # Parse cart data
    cart_json = form_data.get("cart")
    if not cart_json:
        return JSONResponse({"success": False, "error": "Cart is empty"}, status_code=400)
    
    try:
        cart_items = json.loads(cart_json)
    except json.JSONDecodeError:
        return JSONResponse({"success": False, "error": "Invalid cart data"}, status_code=400)
    
    if not cart_items:
        return JSONResponse({"success": False, "error": "Cart is empty"}, status_code=400)
    
    # Calculate total amount
    total_amount = sum(item["price"] * item["quantity"] for item in cart_items)
    
    # Get selected payment method
    payment_method = form_data.get("payment_method", "cash")
    
    # Create an address entry for this order
    address_id = None
    save_address = form_data.get("save_address") == "on"
    address_name = form_data.get("address_name", "Order Address")
    
    # If address_name is not provided, use a default name
    if not address_name:
        address_name = "Default Address" if save_address else "Order Address"
    
    # Make save_address always False for guest users
    if not current_user:
        save_address = False
    
    try:
        # Log the address data for debugging
        print(f"Creating address with data: {shipping_address}")
        
        # Ensure database is initialized
        from app.database import initialize_mongodb
        await initialize_mongodb()
        
        # Create a new address
        new_address = Address(
            id=str(uuid4()),
            # Only link to user if they want to save it and are logged in
            user_id=str(current_user.id) if save_address and current_user else None,
            name=address_name if save_address else "Order Address",
            address=shipping_address.get("address", ""),
            city=shipping_address.get("city", ""),
            country=shipping_address.get("country", "Uganda"),
            is_default=False
        )
        
        # If we're saving to the user's account, check if it should be default
        if save_address and current_user:
            existing_addresses = await Address.find({"user_id": str(current_user.id)}).to_list()
            
            if not existing_addresses:
                new_address.is_default = True
        
        # Log that we're about to save the address
        print(f"About to save address: {new_address.id}")
        await new_address.save()
        address_id = str(new_address.id)
        print(f"Address saved successfully with ID: {address_id}")
        
    except Exception as e:
        import traceback
        print(f"Error saving address: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return JSONResponse(
            {"success": False, "error": f"Error saving address: {str(e)}"},
            status_code=500
        )
    
    # Create the order directly
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            # Get a unique order number
            order_no = await create_unique_order_number()
            if not order_no:
                return JSONResponse(
                    {"success": False, "error": "Unable to generate unique order number"},
                    status_code=500
                )
            
            # Get current time
            current_time = get_eat_time()
            
            # Create the order
            db_order = Order(
                id=str(uuid4()),
                order_no=order_no,
                # Use None for user_id if guest checkout
                user_id=str(current_user.id) if current_user else None,
                # Store guest user email if provided
                guest_email=None if current_user else customer_email,
                # Store guest user data
                guest_data=None if current_user else {
                    "name": customer_name,
                    "email": customer_email,
                    "phone": customer_phone
                },
                # Create shipping address object
                shipping_address=ShippingAddress(
                    street=shipping_address.get("address", ""),
                    city=shipping_address.get("city", ""),
                    state="",  # Optional field
                    postal_code="",  # Optional field
                    country=shipping_address.get("country", "Uganda"),
                    phone=customer_phone
                ),
                # Create order items list
                items=[
                    OrderItem(
                        product_id=item["id"],
                        product_name=item.get("name", "Product"),
                        quantity=item["quantity"],
                        unit_price=float(item["price"]),
                        total_price=float(item["price"] * item["quantity"])
                    )
                    for item in cart_items
                ],
                address_id=address_id,
                total_amount=float(total_amount),
                payment_method=payment_method,
                amount_paid=0,  # Default to 0 paid
                status=OrderStatus.PENDING,
                payment_status=PaymentStatus.PENDING,
                created_at=current_time.replace(tzinfo=None),
                updated_at=current_time.replace(tzinfo=None)
            )
            
            await db_order.save()
            
            # Add order items
            for item in cart_items:
                try:
                    # Check if product exists first
                    product = await Product.find_one({"id": item["id"]})
                    
                    # Only add item if product exists
                    if product:
                        db_item = OrderItem(
                            id=str(uuid4()),
                            order_id=str(db_order.id),
                            product_id=item["id"],
                            quantity=item["quantity"]
                        )
                        await db_item.save()
                        
                        # Increment view_count for the product
                        if not hasattr(product, 'view_count') or product.view_count is None:
                            product.view_count = 0
                        product.view_count += 1
                        
                        # Increment sales_count for the product
                        if not hasattr(product, 'sales_count') or product.sales_count is None:
                            product.sales_count = 0
                        product.sales_count += item["quantity"]
                        
                        await product.save()
                    else:
                        # Product doesn't exist, log the error
                        print(f"Product with ID {item['id']} not found, skipping item")
                except Exception as item_error:
                    print(f"Error adding order item: {item_error}")
                    # Continue with other items instead of failing the entire order
            
            # Return success response
            return JSONResponse({
                "success": True,
                "order_id": str(db_order.id),
                "order_no": order_no,
                "total_amount": total_amount
            })
            
        except Exception as e:
            print(f"Error creating order: {e}")
            return JSONResponse(
                {"success": False, "error": f"Error creating order: {str(e)}"},
                status_code=500
            )
    
    # If we get here, all retries failed
    return JSONResponse(
        {"success": False, "error": "Unable to create order after multiple attempts"},
        status_code=500
    )

@router.post("/api/checkout")
async def api_process_order(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    API endpoint for processing checkout
    Supports both authenticated users and guest checkout
    """
    try:
        # Get request data
        data = await request.json()
        user_info = data.get("user_info", {})
        address_data = data.get("address", {})
        
        # Validate basic required fields
        if not user_info.get("email") or not address_data.get("address"):
            return JSONResponse(
                {"success": False, "message": "Missing required fields"}, 
                status_code=400
            )
        
        # Get cart from session or create empty one
        cart_data = request.session.get("cart", [])
        if not cart_data:
            return JSONResponse(
                {"success": False, "message": "Cart is empty"}, 
                status_code=400
            )
        
        # Check if the user wants to save the address (only for authenticated users)
        save_address = address_data.get("save_address", False) and current_user is not None
        address_name = address_data.get("address_name", "Home") if save_address else None
        
        # Create or get address
        address_id = None
        if current_user:
            # For authenticated users, save address if requested
            if save_address:
                try:
                    address = Address(
                        id=str(uuid4()),
                        user_id=str(current_user.id),
                        name=address_name,
                        address=address_data.get("address"),
                        city=address_data.get("city"),
                        country=address_data.get("country"),
                    )
                    await address.save()
                    address_id = str(address.id)
                except Exception as e:
                    logger.error(f"Error saving address: {e}")
                    return JSONResponse(
                        {"success": False, "message": f"Error saving address: {str(e)}"},
                        status_code=500,
                    )
            
            # If user has selected an existing address from dropdown
            # (This would need to be modified in frontend to support this flow)
            elif address_data.get("address_id"):
                address_id = address_data.get("address_id")
        
        # Generate unique order number
        order_no = None
        for _ in range(5):  # Try 5 times to generate a unique order number
            candidate = generate_order_number()
            existing = await Order.find_one({"order_no": candidate})
            if not existing:
                order_no = candidate
                break
        
        if not order_no:
            return JSONResponse(
                {"success": False, "message": "Unable to generate unique order number"},
                status_code=500,
            )
        
        # Calculate totals
        total_amount = sum(
            item.get("price", 0) * item.get("quantity", 0) for item in cart_data
        )
        
        # Create the order
        try:
            # Create new order record
            new_order = Order(
                id=str(uuid4()),
                order_no=order_no,
                user_id=str(current_user.id) if current_user else None,
                guest_email=None if current_user else user_info.get("email"),
                guest_data=None if current_user else {
                    "name": user_info.get("name"),
                    "email": user_info.get("email"),
                    "phone": user_info.get("phone")
                },
                address_id=address_id,
                total_amount=total_amount,
                status="PENDING",
            )
            
            # If no saved address, create a temporary address and link to order
            if not address_id:
                temp_address = Address(
                    id=str(uuid4()),
                    user_id=str(current_user.id) if current_user else None,
                    name="Order Address",
                    address=address_data.get("address"),
                    city=address_data.get("city"),
                    country=address_data.get("country"),
                )
                await temp_address.save()
                new_order.address_id = str(temp_address.id)
            
            await new_order.save()
            
            # Add order items
            for item in cart_data:
                try:
                    # Check if product exists first
                    product = await Product.find_one({"id": item["id"]})
                    
                    # Only add item if product exists
                    if product:
                        db_item = OrderItem(
                            id=str(uuid4()),
                            order_id=str(new_order.id),
                            product_id=item["id"],
                            quantity=item["quantity"],
                            price=item["price"]
                        )
                        await db_item.save()
                        
                        # Increment view_count for the product
                        if not hasattr(product, 'view_count') or product.view_count is None:
                            product.view_count = 0
                        product.view_count += 1
                        
                        # Increment sales_count for the product
                        if not hasattr(product, 'sales_count') or product.sales_count is None:
                            product.sales_count = 0
                        product.sales_count += item["quantity"]
                        
                        await product.save()
                    else:
                        # Product doesn't exist, log the error
                        print(f"Product with ID {item['id']} not found, skipping item")
                except Exception as item_error:
                    print(f"Error adding order item: {item_error}")
                    # Continue with other items instead of failing the entire order
            
            # Clear the cart
            request.session["cart"] = []
            await request.session.save()
            
            # Return success response
            return JSONResponse(
                {
                    "success": True,
                    "message": "Order created successfully",
                    "order_id": str(new_order.id),
                    "order_no": order_no,
                },
                status_code=201,
            )
        
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return JSONResponse(
                {"success": False, "message": f"Error creating order: {str(e)}"},
                status_code=500,
            )
            
    except Exception as e:
        logger.error(f"Error in checkout process: {e}")
        return JSONResponse(
            {"success": False, "message": "An error occurred during checkout"},
            status_code=500,
        )

