from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.database import get_db, initialize_mongodb
from app.models.order import Order, OrderCreate, OrderStatus, OrderItem, ShippingAddress, PaymentStatus
from app.models.user import User
from app.models.address import Address
from app.models.product import Product
from app.auth.jwt import get_current_active_client
from app.client.checkout import router, templates
from app.utils.time import get_eat_time
import json
from uuid import uuid4
from datetime import datetime
import random
import string
import logging
from typing import Optional, List, Dict, Any, Union
import asyncio

# Import API functions from api.py
from app.client.checkout.api import process_order, update_product_stats

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
    current_user: Optional[User] = Depends(get_current_active_client)
):
    """Checkout page that works with both logged-in users and guests."""
    try:
        # If user is logged in, load their addresses
        user_addresses = []
        if current_user:
            user_addresses = await Address.find({"user_id": str(current_user.id)}).to_list()
            logger.info(f"Loaded {len(user_addresses)} addresses for user {current_user.username}")
        
        # Get cart from session
        cart = request.session.get("cart", [])
        
        return templates.TemplateResponse(
            "checkout/checkout.html", 
            {
                "request": request, 
                "current_user": current_user,
                "addresses": user_addresses,
                "cart": cart
            }
        )
    except Exception as e:
        logger.error(f"Error loading checkout page: {e}")
        return templates.TemplateResponse(
            "checkout/checkout.html",
            {
                "request": request,
                "current_user": current_user,
                "addresses": [],
                "cart": [],
                "error": "An error occurred loading the checkout page. Please try again."
            }
        )

# Note: The API endpoints process_order and api_checkout have been moved to api.py