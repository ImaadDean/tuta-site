from fastapi import APIRouter, Request, Depends, HTTPException, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload , selectinload
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.order import Order, OrderStatus, OrderItem
from app.models.user import User
from app.auth.jwt import get_optional_user, ensure_guest_user
from app.client.orders import router, templates
from typing import Optional
from datetime import datetime

@router.get("/my-orders", response_class=HTMLResponse)
async def get_client_orders(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_optional_user),
    guest_id: str = Depends(ensure_guest_user)
):
    """
    Retrieve all orders associated with the authenticated client or guest.
    Renders a template with the list of orders.
    """
    if user:
        # For authenticated users
        query = select(Order).filter(
            Order.user_id == user.id
        ).order_by(Order.created_at.desc())
    else:
        # For guest users
        query = select(Order).filter(
            Order.guest_id == guest_id
        ).order_by(Order.created_at.desc())
    
    result = await db.execute(query)
    orders = result.scalars().all()
    
    return templates.TemplateResponse(
        "orders/my_orders.html", 
        {
            "request": request, 
            "orders": orders,
            "user": user,
            "is_guest": user is None,
            "guest_id": guest_id if not user else None
        }
    )

@router.get("/orders/filter", response_class=HTMLResponse)
async def filter_client_orders(
    request: Request,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_optional_user),
    guest_id: str = Depends(ensure_guest_user)
):
    """
    Filter orders by status for both authenticated and guest users.
    """
    # Base query
    if user:
        query = select(Order).filter(Order.user_id == user.id)
    else:
        query = select(Order).filter(Order.guest_id == guest_id)
    
    # Apply status filter if provided
    if status:
        query = query.filter(Order.status == status)
    
    # Execute query and order by creation date (newest first)
    query = query.order_by(Order.created_at.desc())
    result = await db.execute(query)
    orders = result.scalars().all()
    
    return templates.TemplateResponse(
        "orders/my_orders.html", 
        {
            "request": request, 
            "orders": orders,
            "user": user,
            "is_guest": user is None,
            "guest_id": guest_id if not user else None,
            "current_status": status
        }
    )

@router.get("/order/{order_id}", response_class=HTMLResponse)
async def get_order_details(
    request: Request,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_optional_user),
    guest_id: str = Depends(ensure_guest_user)
):
    """
    Retrieve details of a specific order by ID for both authenticated and guest users.
    """
    # Build the query with eager loading
    if user:
        query = select(Order).options(
            selectinload(Order.order_items).selectinload(OrderItem.product)
        ).filter(
            Order.id == order_id, 
            Order.user_id == user.id
        )
    else:
        query = select(Order).options(
            selectinload(Order.order_items).selectinload(OrderItem.product)
        ).filter(
            Order.id == order_id, 
            Order.guest_id == guest_id
        )
    
    result = await db.execute(query)
    order = result.scalars().first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return templates.TemplateResponse(
        "orders/order_view.html", 
        {
            "request": request, 
            "order": order, 
            "user": user,
            "is_guest": user is None,
            "guest_id": guest_id if not user else None
        }
    )

@router.post("/cancel-order/{order_id}")
async def cancel_order(
    order_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_optional_user),
    guest_id: str = Depends(ensure_guest_user)
):
    """
    Cancel an existing order if its status is 'pending' for both authenticated and guest users.
    """
    # Find the order
    if user:
        query = select(Order).filter(
            Order.id == order_id,
            Order.user_id == user.id
        )
    else:
        query = select(Order).filter(
            Order.id == order_id,
            Order.guest_id == guest_id
        )
    
    result = await db.execute(query)
    order = result.scalars().first()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Order not found"
        )
    
    # Check if order can be cancelled
    if order.status != OrderStatus.PENDING.value:
        # Return to order page with error
        return templates.TemplateResponse(
            "orders/order_view.html", 
            {
                "request": request, 
                "order": order, 
                "user": user,
                "is_guest": user is None,
                "guest_id": guest_id if not user else None,
                "error": "Only pending orders can be cancelled"
            },
            status_code=400
        )
    
    # Update order status to cancelled
    order.status = OrderStatus.CANCELLED.value
    order.updated_at = datetime.utcnow()
    await db.commit()
    
    # Redirect back to order page
    return RedirectResponse(
        url=f"/order/{order_id}", 
        status_code=status.HTTP_303_SEE_OTHER
    )
