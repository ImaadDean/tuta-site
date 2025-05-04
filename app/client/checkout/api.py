from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from app.database import initialize_mongodb
from app.models.order import Order, OrderStatus, OrderItem, ShippingAddress, PaymentStatus
from app.models.user import User
from app.models.address import Address
from app.models.product import Product
from app.client.checkout import router
from app.auth.jwt import get_current_user_optional, get_current_active_client
from app.utils.time import get_eat_time
import json
from uuid import uuid4
import logging
from typing import Optional, Dict, List
import asyncio

# Set up logger
logger = logging.getLogger(__name__)

# Pre-define characters for order number generation to avoid recreating this list repeatedly
ORDER_NUMBER_CHARS = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'

def generate_order_number() -> str:
    """Generate a unique 5-character order number."""
    import random
    return ''.join(random.choices(ORDER_NUMBER_CHARS, k=5))

async def create_unique_order_number(max_attempts: int = 10) -> Optional[str]:
    """
    Create a unique order number with retry logic.
    Returns None if unable to generate a unique number after max_attempts.
    """
    for _ in range(max_attempts):
        order_no = generate_order_number()
        # Check if order number exists - fixed to not use projection parameter
        existing = await Order.find_one({"order_no": order_no})
        if not existing:
            return order_no
    return None

@router.post("/api/process-order")
async def process_order(
    request: Request,
    current_user: Optional[User] = Depends(get_current_active_client)
):
    """
    Process order via API endpoint, returning JSON response.
    This endpoint is designed for AJAX requests.
    Supports both authenticated users and guest checkout.
    """
    try:
        form_data = await request.form()
        
        # Get selected address ID if user is selecting a saved address
        selected_address_id = form_data.get("selected_address_id")
        
        # Parse cart data early to fail fast if invalid
        cart_json = form_data.get("cart")
        if not cart_json:
            return JSONResponse({"success": False, "error": "Cart is empty"}, status_code=400)
        
        try:
            cart_items = json.loads(cart_json)
        except json.JSONDecodeError:
            return JSONResponse({"success": False, "error": "Invalid cart data"}, status_code=400)
        
        if not cart_items:
            return JSONResponse({"success": False, "error": "Cart is empty"}, status_code=400)
        
        # Get form data for shipping address
        address = {
            "name": form_data.get("name"),
            "address": form_data.get("address"),
            "city": form_data.get("city"),
            "country": form_data.get("country", "Uganda"),  # Default to Uganda if not provided
        }
        
        # Get customer info for guest users
        customer_name = form_data.get("name", "")
        customer_email = form_data.get("email", "")
        customer_phone = form_data.get("phone", "")
        
        # Calculate total amount
        total_amount = sum(item["price"] * item["quantity"] for item in cart_items)
        
        # Get selected payment method
        payment_method = form_data.get("payment_method", "cash")
        
        # Handle address logic
        address_id = None
        shipping_address_obj = None
        
        # Start order number generation early in parallel
        order_no_task = asyncio.create_task(create_unique_order_number())
        
        # If user is logged in and selected an existing address, use that address ID
        if current_user and selected_address_id:
            # Verify the address belongs to the user
            existing_address = await Address.find_one({
                "id": selected_address_id,
                "user_id": str(current_user.id)
            })
            
            if existing_address:
                address_id = selected_address_id
                # Create shipping address object directly from existing address
                shipping_address_obj = ShippingAddress(
                    street=existing_address.address,
                    city=existing_address.city,
                    state="",  # Optional field
                    postal_code="",  # Optional field
                    country=existing_address.country,
                    phone=customer_phone
                )
            else:
                logger.warning(f"Address ID {selected_address_id} not found for user {current_user.id}")
                return JSONResponse(
                    {"success": False, "error": "Selected address not found"},
                    status_code=400
                )
        else:
            # Create a new address if no existing address was selected
            save_address = form_data.get("save_address") == "on"
            address_name = form_data.get("address_name", "Order Address")
            
            # If address_name is not provided, use a default name
            if not address_name:
                address_name = "Default Address" if save_address else "Order Address"
            
            # Make save_address always False for guest users
            if not current_user:
                save_address = False
            
            # Validate that required address fields are present when creating a new address
            required_fields = ["address", "city"]
            for field in required_fields:
                if not address.get(field):
                    return JSONResponse(
                        {"success": False, "error": f"Missing required field: {field}"},
                        status_code=400
                    )
            
            # Create shipping address object from form data
            shipping_address_obj = ShippingAddress(
                street=address.get("address", ""),
                city=address.get("city", ""),
                state="",  # Optional field
                postal_code="",  # Optional field
                country=address.get("country", "Uganda"),
                phone=customer_phone
            )
            
            try:
                # Create a new address only if we need to save it
                if save_address and current_user:
                    # Ensure database is initialized
                    await initialize_mongodb()
                    
                    # Create a new address
                    new_address = Address(
                        id=str(uuid4()),
                        user_id=str(current_user.id),
                        name=address_name,
                        address=address.get("address", ""),
                        city=address.get("city", ""),
                        country=address.get("country", "Uganda"),
                        is_default=False
                    )
                    
                    # Check if it should be default - fixed to not use projection parameter
                    existing_addresses = await Address.find(
                        {"user_id": str(current_user.id)}
                    ).to_list()
                    
                    if not existing_addresses:
                        new_address.is_default = True
                    
                    await new_address.save()
                    address_id = str(new_address.id)
                
            except Exception as e:
                logger.error(f"Error saving address: {e}")
                return JSONResponse(
                    {"success": False, "error": f"Error saving address: {str(e)}"},
                    status_code=500
                )
        
        # Wait for order number generation to complete
        order_no = await order_no_task
        if not order_no:
            return JSONResponse(
                {"success": False, "error": "Unable to generate unique order number"},
                status_code=500
            )
        
        # Get current time
        current_time = get_eat_time()
        
        # Prepare order items
        order_items = [
            OrderItem(
                product_id=item["id"],
                product_name=item.get("name", "Product"),
                quantity=item["quantity"],
                unit_price=float(item["price"]),
                total_price=float(item["price"] * item["quantity"]),
                # Add variant information
                variant_id=item.get("variantId"),
                variant_details=item.get("variantDetails", []),
                variant_display=item.get("variantDisplay", "")
            )
            for item in cart_items
        ]
        
        # Create the order
        try:
            # Create the order
            db_order = Order(
                id=str(uuid4()),
                order_no=order_no,
                user_id=str(current_user.id) if current_user else None,
                guest_email=None if current_user else customer_email,
                guest_data=None if current_user else {
                    "name": customer_name,
                    "email": customer_email,
                    "phone": customer_phone
                },
                shipping_address=shipping_address_obj,
                items=order_items,
                address_id=address_id,
                total_amount=float(total_amount),
                payment_method=payment_method,
                amount_paid=0,  # Default to 0 paid
                status=OrderStatus.PENDING,
                payment_status=PaymentStatus.PENDING,
                created_at=current_time.replace(tzinfo=None),
                updated_at=current_time.replace(tzinfo=None)
            )
            
            # Save the order
            await db_order.save()
            
            # Update product stats in the background without waiting
            asyncio.create_task(update_product_stats(cart_items))
            
            # Return success response immediately
            return JSONResponse({
                "success": True,
                "order_id": str(db_order.id),
                "order_no": order_no,
                "total_amount": total_amount
            })
                
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return JSONResponse(
                {"success": False, "error": f"Error creating order: {str(e)}"},
                status_code=500
            )
    
    except Exception as e:
        logger.error(f"Unexpected error in API process order: {e}")
        return JSONResponse(
            {"success": False, "error": "An unexpected error occurred during checkout"},
            status_code=500
        )

async def update_product_stats(cart_items: List[Dict]):
    """
    Update product statistics in the background.
    This function is meant to be called with asyncio.create_task() to run in the background.
    """
    try:
        for item in cart_items:
            try:
                # Check if product exists first
                product = await Product.find_one({"id": item["id"]})
                
                # Only update if product exists
                if product:
                    # Increment view_count for the product
                    if not hasattr(product, 'view_count') or product.view_count is None:
                        product.view_count = 0
                    product.view_count += 1
                    
                    # Increment sales_count for the product
                    if not hasattr(product, 'sales_count') or product.sales_count is None:
                        product.sales_count = 0
                    product.sales_count += item["quantity"]
                    
                    await product.save()
            except Exception as item_error:
                logger.error(f"Error updating product stats: {item_error}")
                # Continue with other items instead of failing the entire process
    except Exception as e:
        logger.error(f"Error in background product stats update: {e}")
