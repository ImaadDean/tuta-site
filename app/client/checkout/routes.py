from fastapi import APIRouter, Request, Depends, HTTPException, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func, text
from app.database import get_db
from app.models.order import Order, OrderCreate, OrderStatus, OrderItem
from app.models.user import User
from app.auth.jwt import get_optional_user, ensure_guest_user
from app.client.checkout import router, templates
from app.utils.time import get_eat_time
import json
from uuid import uuid4
from datetime import datetime
import random
import string
from sqlalchemy.exc import IntegrityError
from typing import Optional

def generate_order_number() -> str:
    """Generate a unique 5-character order number."""
    # Use uppercase letters and numbers, excluding similar-looking characters
    chars = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'
    return ''.join(random.choices(chars, k=5))

async def create_unique_order_number(db: AsyncSession, max_attempts: int = 10) -> Optional[str]:
    """
    Create a unique order number with retry logic.
    Returns None if unable to generate a unique number after max_attempts.
    """
    for _ in range(max_attempts):
        order_no = generate_order_number()
        # Check if order number exists using async API
        result = await db.execute(select(Order).filter(Order.order_no == order_no))
        existing = result.scalars().first()
        if not existing:
            return order_no
    return None


@router.get("/checkout", response_class=HTMLResponse)
async def checkout_page(
    request: Request, 
    response: Response,
    user = Depends(get_optional_user),
    guest_id: str = Depends(ensure_guest_user)
):
    """
    Checkout page that works for both authenticated and guest users
    """
    return templates.TemplateResponse(
        "checkout/checkout.html", 
        {
            "request": request, 
            "user": user,
            "guest_id": guest_id if not user else None,
            "is_guest": user is None
        }
    )

@router.post("/checkout")
async def process_checkout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_optional_user),
    guest_id: str = Depends(ensure_guest_user)
):
    """
    Process checkout for both authenticated and guest users
    """
    form_data = await request.form()
    
    # Get shipping information
    shipping_address = {
        "name": form_data.get("name"),
        "email": form_data.get("email"),  # Added email for guest users
        "address": form_data.get("address"),
        "city": form_data.get("city"),
        "country": form_data.get("country"),
        "postal_code": form_data.get("postal_code"),
    }
    
    # Validate email for guest users
    if not user and not shipping_address.get("email"):
        raise HTTPException(status_code=400, detail="Email is required for guest checkout")
    
    # Get cart data
    cart_json = form_data.get("cart")
    if not cart_json:
        raise HTTPException(status_code=400, detail="Cart is empty")
    
    try:
        cart_items = json.loads(cart_json)
        print("Cart items:", cart_items)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid cart data")
    
    total_amount = sum(item["price"] * item["quantity"] for item in cart_items)
    
    # Generate a temporary order ID
    temp_order_id = str(uuid4())
    
    # Store the order details in the session
    request.session["temp_order"] = {
        "id": temp_order_id,
        "user_id": str(user.id) if user else None,
        "guest_id": guest_id if not user else None,
        "is_guest": user is None,
        "total_amount": total_amount,
        "shipping_address": shipping_address,
        "cart_items": cart_items,
        "email": shipping_address.get("email")
    }
    
    return RedirectResponse(url=f"/order-confirmation/{temp_order_id}", status_code=303)

@router.get("/order-confirmation/{temp_order_id}", response_class=HTMLResponse)
async def order_confirmation(
    request: Request,
    temp_order_id: str,
    user = Depends(get_optional_user)
):
    """
    Order confirmation page for both authenticated and guest users
    """
    temp_order = request.session.get("temp_order")
    if not temp_order or temp_order["id"] != temp_order_id:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Extract the items from the order and pass them separately
    order_items = temp_order.get("cart_items", [])
    
    print("Order items:", order_items)
    
    return templates.TemplateResponse(
        "checkout/order_confirmation.html", 
        {
            "request": request, 
            "order": temp_order, 
            "order_items": order_items,
            "user": user,
            "is_guest": temp_order.get("is_guest", False)
        }
    )


@router.post("/confirm-order/{temp_order_id}")
async def confirm_order(
    request: Request,
    temp_order_id: str,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_optional_user)
):
    """
    Confirm order for both authenticated and guest users
    """
    temp_order = request.session.get("temp_order")
    if not temp_order or temp_order["id"] != temp_order_id:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Transform cart items to match OrderItemCreate format
    order_items = []
    for item in temp_order.get("cart_items", []):
        order_items.append({
            "product_id": item["id"],
            "quantity": item["quantity"]
        })
    
    max_retries = 3  # Maximum number of retries for the entire order creation
    for attempt in range(max_retries):
        try:
            # Get a unique order number
            order_no = await create_unique_order_number(db)
            if not order_no:
                raise HTTPException(
                    status_code=500,
                    detail="Unable to generate unique order number. Please try again."
                )
            
            # Get current time - now returns timezone-naive datetime
            current_time = get_eat_time()
            
            # Create the order with timezone-naive datetimes
            db_order = Order(
                id=str(uuid4()),
                order_no=order_no,
                user_id=user.id if user else None,
                guest_id=temp_order.get("guest_id") if not user else None,
                guest_email=temp_order.get("shipping_address", {}).get("email") if not user else None,
                total_amount=temp_order["total_amount"],
                shipping_address=temp_order["shipping_address"],
                status=OrderStatus.PENDING.value,
                created_at=current_time,
                updated_at=current_time
            )
            db.add(db_order)
            await db.flush()  # Flush to get the order ID
            
            # Add order items
            for item_data in order_items:
                db_item = OrderItem(
                    order_id=db_order.id,
                    product_id=item_data["product_id"],
                    quantity=item_data["quantity"]
                )
                db.add(db_item)
            
            await db.commit()
            
            # Clear the temporary order and cart from the session
            del request.session["temp_order"]
            request.session["cart"] = []
            
            return RedirectResponse(url=f"/check/order/{db_order.id}", status_code=303)
            
        except IntegrityError as e:
            await db.rollback()  # Use await here
            # If this was our last attempt, raise the error
            if attempt == max_retries - 1:
                print(f"Failed to create order after {max_retries} attempts: {e}")
                raise HTTPException(
                    status_code=500,
                    detail="Unable to create order due to conflict. Please try again."
                )
            continue  # Try again with a new order number
            
        except Exception as e:
            await db.rollback()  # Use await here
            print(f"Error creating order: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error creating order: {str(e)}"
            )

@router.get("/check/order/{order_id}", response_class=HTMLResponse)
async def view_order(
    request: Request,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_optional_user),
    guest_id: str = Depends(ensure_guest_user)
):
    """
    View order details for both authenticated and guest users
    """
    # Use selectinload for async SQLAlchemy
    from sqlalchemy.orm import selectinload
    
    # Build the query with eager loading
    if user:
        # For authenticated users, check user_id
        query = select(Order).options(
            selectinload(Order.order_items).selectinload(OrderItem.product)
        ).filter(
            Order.id == order_id, 
            Order.user_id == user.id
        )
    else:
        # For guest users, check guest_id
        query = select(Order).options(
            selectinload(Order.order_items).selectinload(OrderItem.product)
        ).filter(
            Order.id == order_id, 
            Order.guest_id == guest_id
        )
    
    # Execute the query
    result = await db.execute(query)
    order = result.scalars().first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Print for debugging
    print(f"Order: {order}")
    print(f"Order items: {order.order_items}")
    
    return templates.TemplateResponse(
        "checkout/order_view.html", 
        {
            "request": request, 
            "order": order, 
            "user": user,
            "is_guest": user is None,
            "guest_id": guest_id if not user else None
        }
    )

# Add a new endpoint to search orders by order_no
@router.get("/search-order", response_class=HTMLResponse)
async def search_order_page(
    request: Request,
    user = Depends(get_optional_user),
    guest_id: str = Depends(ensure_guest_user)
):
    """
    Search order page for both authenticated and guest users
    """
    return templates.TemplateResponse(
        "checkout/search_order.html", 
        {
            "request": request, 
            "user": user,
            "is_guest": user is None,
            "guest_id": guest_id if not user else None
        }
    )


# Update the search order function too
@router.post("/search-order")
async def search_order(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_optional_user),
    guest_id: str = Depends(ensure_guest_user)
):
    """
    Search for orders by order number for both authenticated and guest users
    """
    form_data = await request.form()
    order_no = form_data.get("order_no")
    email = form_data.get("email")  # Added for guest users
    
    if not order_no:
        raise HTTPException(status_code=400, detail="Order number is required")
    
    # For admin users, allow searching any order
    if user and user.is_admin:
        query = select(Order).options(
            selectinload(Order.order_items).selectinload(OrderItem.product)
        ).filter(Order.order_no == order_no)
    elif user:
        # For regular users, only allow searching their own orders
        query = select(Order).options(
            selectinload(Order.order_items).selectinload(OrderItem.product)
        ).filter(
            Order.order_no == order_no,
            Order.user_id == user.id
        )
    else:
        # For guest users, require email and check guest_id
        if not email:
            return templates.TemplateResponse(
                "checkout/search_order.html",
                {
                    "request": request,
                    "user": user,
                    "is_guest": True,
                    "guest_id": guest_id,
                    "error": "Email is required for guest order lookup"
                }
            )
        
        query = select(Order).options(
            selectinload(Order.order_items).selectinload(OrderItem.product)
        ).filter(
            Order.order_no == order_no,
            Order.guest_id == guest_id,
            Order.guest_email == email
        )
    
    result = await db.execute(query)
    order = result.scalars().first()
    
    if not order:
        return templates.TemplateResponse(
            "checkout/search_order.html",
            {
                "request": request,
                "user": user,
                "is_guest": user is None,
                "guest_id": guest_id if not user else None,
                "error": "Order not found"
            }
        )
    
    return RedirectResponse(url=f"/check/order/{order.id}", status_code=303)

