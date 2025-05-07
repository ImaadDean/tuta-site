from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import RedirectResponse, JSONResponse
from typing import Optional
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.user import User
from app.auth.jwt import get_current_active_admin
from app.admin.order import router, templates
import logging

# Configure logging
logger = logging.getLogger(__name__)

def format_money(amount: float) -> str:
    """Format money values with commas (e.g., 10000.0 -> 10,000)"""
    if amount is None:
        return "UGX 0"
    return f"UGX {int(amount):,}"

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

        # Create a list to store orders with formatted values
        formatted_orders = []

        # Process each order
        for order in orders:
            # Create a dictionary with the order data
            order_dict = {
                "id": order.id,
                "order_no": order.order_no,
                "created_at": order.created_at,
                "user_id": order.user_id,
                "guest_email": order.guest_email,
                "guest_data": order.guest_data,
                "total_amount": order.total_amount,
                "amount_paid": order.amount_paid,
                "payment_status": order.payment_status,
                "status": order.status,

                # Add formatted values
                "formatted_total_amount": format_money(order.total_amount),
                "formatted_amount_paid": format_money(order.amount_paid)
            }

            # Calculate payment percentage
            if order.total_amount > 0:
                order_dict["payment_percentage"] = min(100, int((order.amount_paid / order.total_amount) * 100))
            else:
                order_dict["payment_percentage"] = 0

            # Get user information if available
            if order.user_id:
                user = await User.find_one({"_id": order.user_id})
                if user:
                    order_dict["user"] = user

            formatted_orders.append(order_dict)

        return templates.TemplateResponse(
            "orders/list.html",
            {
                "request": request,
                "orders": formatted_orders,
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

        # Calculate the remaining amount
        remaining_amount = max(0, order.total_amount - order.amount_paid)

        # Calculate the payment percentage
        payment_percentage = 0
        if order.total_amount > 0:
            payment_percentage = min(100, int((order.amount_paid / order.total_amount) * 100))

        # Format money values for display
        formatted_values = {
            "amount_paid": format_money(order.amount_paid),
            "total_amount": format_money(order.total_amount),
            "remaining_amount": format_money(remaining_amount),
            "payment_percentage": payment_percentage
        }

        # Format money values for order items
        formatted_items = []
        for item in order.items:
            formatted_item = {
                "id": item.product_id,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
                "formatted_unit_price": format_money(item.unit_price),
                "formatted_total_price": format_money(item.total_price)
            }

            # Add variant information if available
            if item.variant:
                formatted_item["variant"] = {
                    "id": item.variant.id,
                    "value": item.variant.value,
                    "price": item.variant.price,
                    "formatted_price": format_money(item.variant.price),
                    "discount_percentage": item.variant.discount_percentage
                }

            formatted_items.append(formatted_item)

        return templates.TemplateResponse(
            "orders/detail.html",
            {
                "request": request,
                "order": order,
                "user": current_user,
                "statuses": OrderStatus,
                "formatted_values": formatted_values,
                "formatted_items": formatted_items
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
        logger.info(f"Updating order status: {order_id} to {status}")
        order = await Order.find_one({"_id": order_id})
        if not order:
            logger.error(f"Order not found: {order_id}")
            raise HTTPException(status_code=404, detail="Order not found")

        # Validate status
        try:
            # The status value should already be lowercase from the template
            new_status = OrderStatus(status)
            logger.info(f"New status validated: {new_status}")
        except ValueError as ve:
            logger.error(f"Invalid status: {status}. Error: {str(ve)}")
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        # Update order status
        order.status = new_status
        await order.save()
        logger.info(f"Order status updated successfully: {order_id} to {new_status}")

        return JSONResponse({"status": "success"})
    except HTTPException as he:
        # Re-raise HTTP exceptions
        logger.error(f"HTTP error updating order status: {str(he)}")
        raise
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
        try:
            # Try to convert the string to a PaymentStatus enum
            payment_status_enum = PaymentStatus(payment_status.lower())
            order.payment_status = payment_status_enum
        except ValueError:
            # If it's not a valid enum value, log a warning and use a default
            logger.warning(f"Invalid payment status: {payment_status}. Using 'pending' instead.")
            order.payment_status = PaymentStatus.PENDING

        # Update amount paid if provided - add to existing amount
        if amount_paid is not None:
            # Add the new amount to the existing amount
            previous_amount = order.amount_paid
            order.amount_paid += amount_paid
            logger.info(f"Updated amount_paid: {previous_amount} + {amount_paid} = {order.amount_paid}")

            # If amount paid equals or exceeds total amount, update payment status to fully paid
            if order.amount_paid >= order.total_amount:
                order.payment_status = PaymentStatus.FULLY_PAID
                logger.info(f"Payment status automatically updated to FULLY_PAID as amount_paid >= total_amount")

                # If order is pending, update to processing
                if order.status == OrderStatus.PENDING:
                    order.status = OrderStatus.PROCESSING
                    logger.info(f"Order status automatically updated to PROCESSING")
            # If payment status is pending and some amount is paid, update to partial paid
            elif order.payment_status == PaymentStatus.PENDING and order.amount_paid > 0:
                order.payment_status = PaymentStatus.PARTIAL_PAID
                logger.info(f"Payment status automatically updated to PARTIAL_PAID")

        await order.save()

        # Calculate the remaining amount
        remaining_amount = max(0, order.total_amount - order.amount_paid)

        # Calculate the payment percentage
        payment_percentage = 0
        if order.total_amount > 0:
            payment_percentage = min(100, int((order.amount_paid / order.total_amount) * 100))

        return JSONResponse({
            "status": "success",
            "amount_paid": order.amount_paid,
            "formatted_amount_paid": format_money(order.amount_paid),
            "formatted_total_amount": format_money(order.total_amount),
            "formatted_remaining": format_money(remaining_amount),
            "payment_percentage": payment_percentage,
            "order_status": order.status.value if order.status else None,
            "payment_status": order.payment_status.value if order.payment_status else None
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