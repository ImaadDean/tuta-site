from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import RedirectResponse, JSONResponse
from typing import Optional
from app.models.order import Order, OrderStatus
from app.models.user import User
from app.auth.jwt import get_current_active_admin
from app.admin.order import router, templates
import logging

# Configure logging
logger = logging.getLogger(__name__)

@router.get("/")
async def list_orders(
    request: Request,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_active_admin)
):
    """
    List all orders with optional status filter
    """
    try:
        # Build query based on status filter
        query = {}
        if status:
            query["status"] = status.upper()
        
        # Get orders with user information
        orders = await Order.find(query).sort([("created_at", -1)]).to_list()
        
        # Get user information for each order
        for order in orders:
            user = await User.find_one({"_id": order.user_id})
            if user:
                order.user = user
        
        return templates.TemplateResponse(
            "orders/list.html",
            {
                "request": request,
                "orders": orders,
                "user": current_user,
                "statuses": OrderStatus,
                "current_status": status
            }
        )
    except Exception as e:
        logger.error(f"Error listing orders: {str(e)}")
        return templates.TemplateResponse(
            "orders/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not list orders: {str(e)}"
            },
            status_code=500
        )

@router.get("/{order_id}")
async def view_order(
    request: Request,
    order_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    View order details
    """
    try:
        logger.info(f"Attempting to find order with ID: {order_id}")
        order = await Order.find_one({"_id": order_id})
        if not order:
            logger.warning(f"Order not found with ID: {order_id}")
            return templates.TemplateResponse(
                "orders/404.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "Order not found"
                },
                status_code=404
            )
        
        # Get user information
        user = await User.find_one({"_id": order.user_id})
        if user:
            order.user = user
        
        logger.info(f"Found order: {order.id}")
        return templates.TemplateResponse(
            "orders/detail.html",
            {
                "request": request,
                "order": order,
                "user": current_user,
                "statuses": OrderStatus
            }
        )
    except Exception as e:
        logger.error(f"Error viewing order: {str(e)}")
        return templates.TemplateResponse(
            "orders/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not view order: {str(e)}"
            },
            status_code=500
        )

@router.post("/{order_id}/update-status")
async def update_order_status(
    request: Request,
    order_id: str,
    status: str = Form(...),
    current_user: User = Depends(get_current_active_admin)
):
    """
    Update order status
    """
    try:
        order = await Order.find_one({"_id": order_id})
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Validate status
        try:
            new_status = OrderStatus(status.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status")
        
        # Update order status
        order.status = new_status
        await order.save()
        
        return JSONResponse({"status": "success"})
    except Exception as e:
        logger.error(f"Error updating order status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{order_id}/update-payment")
async def update_payment_status(
    request: Request,
    order_id: str,
    payment_status: str = Form(...),
    amount_paid: Optional[float] = Form(None),
    current_user: User = Depends(get_current_active_admin)
):
    """
    Update order payment status
    """
    try:
        order = await Order.find_one({"_id": order_id})
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Update payment status
        order.payment_status = payment_status.lower()
        
        # Update amount paid if provided
        if amount_paid is not None:
            order.amount_paid = amount_paid
            
            # If fully paid, update order status to processing
            if payment_status.lower() == "fully_paid" and order.status == OrderStatus.PENDING:
                order.status = OrderStatus.PROCESSING
        
        await order.save()
        
        return JSONResponse({
            "status": "success",
            "amount_paid": order.amount_paid,
            "order_status": order.status.value if order.status else None
        })
    except Exception as e:
        logger.error(f"Error updating payment status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{order_id}/cancel")
async def cancel_order(
    request: Request,
    order_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Cancel an order
    """
    try:
        order = await Order.find_one({"_id": order_id})
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Only allow cancellation of pending or processing orders
        if order.status not in [OrderStatus.PENDING, OrderStatus.PROCESSING]:
            raise HTTPException(
                status_code=400,
                detail="Only pending or processing orders can be cancelled"
            )
        
        # Update order status to cancelled
        order.status = OrderStatus.CANCELLED
        await order.save()
        
        return RedirectResponse(
            url="/admin/orders",
            status_code=303
        )
    except Exception as e:
        logger.error(f"Error cancelling order: {str(e)}")
        return templates.TemplateResponse(
            "orders/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not cancel order: {str(e)}"
            },
            status_code=500
        ) 