from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
from app.models.user import User
from app.models.order import Order, OrderStatus, PaymentStatus
from app.auth.jwt import get_current_active_admin
from app.database import get_db
from app.admin.order import router

# Configure logging
logger = logging.getLogger(__name__)

@router.get("/api/get-orders", response_class=JSONResponse)
async def get_dashboard_orders(
    request: Request,
    status: Optional[str] = None,
    payment_status: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 10,
    skip: int = 0,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """API endpoint to fetch recent orders for dashboard with filtering and search"""
    try:
        # Build query based on filters
        query = {}

        # Status filter
        if status:
            query["status"] = status

        # Payment status filter
        if payment_status:
            query["payment_status"] = payment_status

        # Date range filter
        if date_from or date_to:
            date_query = {}
            if date_from:
                try:
                    from_date = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                    date_query["$gte"] = from_date
                except ValueError:
                    pass

            if date_to:
                try:
                    to_date = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                    # Set to end of day
                    to_date = datetime.combine(to_date.date(), datetime.max.time())
                    date_query["$lte"] = to_date
                except ValueError:
                    pass

            if date_query:
                query["created_at"] = date_query

        # Search functionality
        if search and search.strip():
            search_term = search.strip()

            # Create a text search query
            search_query = {
                "$or": [
                    {"order_no": {"$regex": search_term, "$options": "i"}},
                    {"guest_email": {"$regex": search_term, "$options": "i"}},
                ]
            }

            # Also search in guest_data if it exists
            guest_data_query = {
                "$and": [
                    {"guest_data": {"$exists": True}},
                    {"$or": [
                        {"guest_data.name": {"$regex": search_term, "$options": "i"}},
                        {"guest_data.phone": {"$regex": search_term, "$options": "i"}}
                    ]}
                ]
            }

            # Combine with the main query
            if not query:
                query = {"$or": [search_query, guest_data_query]}
            else:
                # If we already have other filters, we need to use $and to combine them
                query = {"$and": [query, {"$or": [search_query, guest_data_query]}]}

        # Get total count for pagination
        total_count = await Order.find(query).count()

        # Get filtered orders with pagination
        orders = await Order.find(query).sort([("created_at", -1)]).skip(skip).limit(limit).to_list()

        # Format orders for API response
        orders_data = []
        for order in orders:
            # Format money values with commas and no decimal places
            formatted_total_amount = f"UGX {int(order.total_amount):,}"
            formatted_amount_paid = f"UGX {int(order.amount_paid):,}"

            # Calculate payment percentage
            payment_percentage = 0
            if order.total_amount > 0:
                payment_percentage = min(100, int((order.amount_paid / order.total_amount) * 100))

            order_data = {
                "id": str(order.id),
                "order_no": order.order_no,
                "total_amount": order.total_amount,
                "amount_paid": order.amount_paid,
                "formatted_total_amount": formatted_total_amount,
                "formatted_amount_paid": formatted_amount_paid,
                "formatted_amount": formatted_total_amount,  # For backward compatibility
                "payment_percentage": payment_percentage,
                "status": order.status,
                "payment_status": order.payment_status,
                "created_at": order.created_at.isoformat(),
                "user_id": order.user_id,
                "guest_email": order.guest_email,
                "guest_data": order.guest_data
            }

            # Add user info if available
            if order.user_id:
                user = await User.find_one({"_id": order.user_id})
                if user:
                    # Make sure we include the phone_number field for users
                    order_data["user"] = {
                        "id": str(user.id),
                        "username": user.username,
                        "email": user.email,
                        "phone_number": user.phone_number if hasattr(user, "phone_number") else None
                    }

            orders_data.append(order_data)

        # Calculate pagination information
        current_page = skip // limit + 1 if limit > 0 else 1
        total_pages = (total_count + limit - 1) // limit if limit > 0 else 1

        return JSONResponse(content={
            "success": True,
            "orders": orders_data,
            "total": total_count,
            "has_more": total_count > (skip + limit),
            "pagination": {
                "current_page": current_page,
                "total_pages": total_pages,
                "limit": limit,
                "skip": skip,
                "items_showing": f"{skip + 1}-{min(skip + limit, total_count)} of {total_count}"
            }
        })
    except Exception as e:
        logger.error(f"Error fetching dashboard orders: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": f"Failed to fetch orders: {str(e)}"}
        )

