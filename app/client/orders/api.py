from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from app.models.order import Order, OrderStatus, PaymentStatus
from app.models.user import User
from app.models.product import Product
from app.auth.jwt import get_current_user, get_current_active_client
from app.client.orders import router
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import math
import logging

# Set up logger
logger = logging.getLogger(__name__)

@router.get("/api/v1/orders")
async def get_orders_api_v1(
    page: int = Query(1, ge=1),
    page_size: int = Query(6, ge=1, le=20),  # Default to 6 items per page
    status: Optional[str] = None,
    payment_status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    API endpoint to get orders for the current user with pagination and filtering.
    Returns a JSON response with order data and pagination information.
    """
    try:
        # Build the query with filters
        query = {"user_id": str(current_user.id)}
        
        # Apply status filter if provided
        if status:
            query["status"] = status
        
        # Apply payment status filter if provided
        if payment_status:
            query["payment_status"] = payment_status
        
        # Apply date range filters if provided
        if date_from:
            try:
                from_date = datetime.strptime(date_from, "%Y-%m-%d")
                query["created_at"] = {"$gte": from_date}
            except ValueError:
                # Invalid date format, ignore this filter
                pass
        
        if date_to:
            try:
                to_date = datetime.strptime(date_to, "%Y-%m-%d")
                # Add one day to include the end date fully
                to_date = to_date + timedelta(days=1)
                if "created_at" in query:
                    query["created_at"]["$lt"] = to_date
                else:
                    query["created_at"] = {"$lt": to_date}
            except ValueError:
                # Invalid date format, ignore this filter
                pass
        
        # Calculate offset for pagination
        skip = (page - 1) * page_size
        
        # Get total count for pagination
        total_count = await Order.find(query).count()
        
        # Calculate total pages
        total_pages = math.ceil(total_count / page_size)
        
        # Get raw orders from MongoDB
        db = Order.get_motor_collection()
        raw_orders = await db.find(query).sort("created_at", -1).skip(skip).limit(page_size).to_list(length=None)
        
        logger.info(f"Found {len(raw_orders)} raw orders for user {current_user.id}")
        
        # Process orders for API response
        orders_data = []
        for raw_order in raw_orders:
            try:
                # Create an Order object from the raw MongoDB document
                order = Order.parse_obj(raw_order)
                
                # Ensure order has an order_no
                if not hasattr(order, "order_no") or not order.order_no:
                    order.order_no = str(order.id)
                
                # Format order data for API response
                order_data = {
                    "id": str(order.id),
                    "order_no": order.order_no,
                    "total_amount": order.total_amount,
                    "status": order.status,
                    "payment_status": order.payment_status,
                    "created_at": order.created_at.isoformat(),
                    "updated_at": order.updated_at.isoformat() if order.updated_at else None,
                    "items": []
                }
                
                # Add items data if available
                if hasattr(order, 'items') and order.items:
                    for item in order.items:
                        item_data = {
                            "product_id": item.product_id,
                            "product_name": item.product_name if hasattr(item, 'product_name') else "Product",
                            "quantity": item.quantity,
                            "unit_price": item.unit_price if hasattr(item, 'unit_price') else 0,
                            "total_price": item.total_price if hasattr(item, 'total_price') else 0
                        }
                        order_data["items"].append(item_data)
                
                # Add shipping address if available
                if hasattr(order, 'shipping_address') and order.shipping_address:
                    order_data["shipping_address"] = {
                        "street": order.shipping_address.street,
                        "city": order.shipping_address.city,
                        "state": order.shipping_address.state,
                        "postal_code": order.shipping_address.postal_code,
                        "country": order.shipping_address.country,
                        "phone": order.shipping_address.phone
                    }
                
                orders_data.append(order_data)
                
            except Exception as e:
                logger.error(f"Error processing order: {e}")
                continue
        
        # Return JSON response with orders data and pagination info
        return JSONResponse({
            "success": True,
            "data": {
                "orders": orders_data,
                "pagination": {
                    "current_page": page,
                    "total_pages": total_pages,
                    "page_size": page_size,
                    "total_items": total_count,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            }
        })
    except Exception as e:
        logger.error(f"Error retrieving orders API: {e}")
        return JSONResponse({
            "success": False,
            "error": f"An error occurred while retrieving orders: {str(e)}"
        }, status_code=500)

@router.get("/api/v1/orders/{order_id}")
async def get_order_details_api_v1(
    order_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    API endpoint to get details of a specific order by ID.
    Returns a JSON response with detailed order information.
    """
    try:
        # Find the order - try both id and _id fields to be safe
        order = await Order.find_one({"$or": [{"id": order_id}, {"_id": order_id}], "user_id": str(current_user.id)})
        
        if not order:
            return JSONResponse({
                "success": False,
                "error": "Order not found"
            }, status_code=404)
        
        # Format order data for API response
        order_data = {
            "id": str(order.id),
            "order_no": order.order_no if hasattr(order, 'order_no') else str(order.id),
            "total_amount": order.total_amount,
            "status": order.status,
            "payment_status": order.payment_status,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
            "items": [],
            "timeline": []
        }
        
        # Add items data if available
        if hasattr(order, 'items') and order.items:
            for item in order.items:
                item_data = {
                    "product_id": item.product_id,
                    "product_name": item.product_name if hasattr(item, 'product_name') else "Product",
                    "quantity": item.quantity,
                    "unit_price": item.unit_price if hasattr(item, 'unit_price') else 0,
                    "total_price": item.total_price if hasattr(item, 'total_price') else 0
                }
                
                # Try to get product details
                try:
                    product = await Product.find_one({"$or": [{"id": item.product_id}, {"_id": item.product_id}]})
                    if product:
                        item_data["product"] = {
                            "id": str(product.id),
                            "name": product.name,
                            "image_url": product.image_urls[0] if product.image_urls and len(product.image_urls) > 0 else None
                        }
                except Exception as e:
                    logger.error(f"Error fetching product details: {e}")
                
                order_data["items"].append(item_data)
        
        # Add shipping address if available
        if hasattr(order, 'shipping_address') and order.shipping_address:
            order_data["shipping_address"] = {
                "street": order.shipping_address.street,
                "city": order.shipping_address.city,
                "state": order.shipping_address.state,
                "postal_code": order.shipping_address.postal_code,
                "country": order.shipping_address.country,
                "phone": order.shipping_address.phone
            }
        
        # Create a timeline based on order status
        timeline = []
        
        # Order placed (always included)
        timeline.append({
            "status": "Order Placed",
            "completed": True,
            "date": order.created_at.isoformat(),
            "description": f"Order #{order.order_no if hasattr(order, 'order_no') else order.id} has been placed successfully."
        })
        
        # Processing
        timeline.append({
            "status": "Processing",
            "completed": order.status in [OrderStatus.PROCESSING, OrderStatus.DELIVERING, OrderStatus.COMPLETED],
            "date": order.updated_at.isoformat() if order.status != OrderStatus.PENDING and order.updated_at else None,
            "description": "Your order is being processed and prepared for shipping."
        })
        
        # Delivering
        timeline.append({
            "status": "Out for Delivery",
            "completed": order.status in [OrderStatus.DELIVERING, OrderStatus.COMPLETED],
            "date": order.updated_at.isoformat() if order.status in [OrderStatus.DELIVERING, OrderStatus.COMPLETED] and order.updated_at else None,
            "description": "Your order is on its way to you."
        })
        
        # Delivered
        timeline.append({
            "status": "Delivered",
            "completed": order.status == OrderStatus.COMPLETED,
            "date": order.updated_at.isoformat() if order.status == OrderStatus.COMPLETED and order.updated_at else None,
            "description": "Your order has been delivered successfully."
        })
        
        # If cancelled, replace the timeline with a cancelled status
        if order.status == OrderStatus.CANCELLED:
            timeline = [{
                "status": "Order Placed",
                "completed": True,
                "date": order.created_at.isoformat(),
                "description": f"Order #{order.order_no if hasattr(order, 'order_no') else order.id} has been placed successfully."
            }, {
                "status": "Order Cancelled",
                "completed": True,
                "date": order.updated_at.isoformat() if order.updated_at else None,
                "description": "This order has been cancelled."
            }]
        
        order_data["timeline"] = timeline
        
        # Return JSON response with order data
        return JSONResponse({
            "success": True,
            "data": order_data
        })
    except Exception as e:
        logger.error(f"Error retrieving order details: {e}")
        return JSONResponse({
            "success": False,
            "error": f"An error occurred while retrieving order details: {str(e)}"
        }, status_code=500)

@router.get("/api/v1/track-order/{order_no}")
async def track_order_api_v1(
    order_no: str,
    current_user: Optional[User] = Depends(get_current_active_client)  # Changed from get_current_active_client
):
    """
    API endpoint to track an order by order number.
    Works for both logged-in users and guests.
    Returns a JSON response with order tracking information.
    """
    try:
        # Build query to find the order
        query = {"order_no": order_no.upper()}
        
        # Find the order
        order = await Order.find_one(query)
        
        if not order:
            return JSONResponse({
                "success": False,
                "error": "Order not found. Please check the order number and try again."
            }, status_code=404)
        
        # Remove this security check to allow any user to track any order
        # if not current_user and order.user_id:
        #     return JSONResponse({
        #         "success": False,
        #         "error": "This order belongs to a registered user. Please log in to view details."
        #     }, status_code=403)
        
        # Format order data for API response
        order_data = {
            "id": str(order.id),
            "order_no": order.order_no if hasattr(order, 'order_no') else str(order.id),
            "total_amount": order.total_amount,
            "status": order.status,
            "payment_status": order.payment_status,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
            "items": [],
            "timeline": []
        }
        
        # Add items data if available
        if hasattr(order, 'items') and order.items:
            for item in order.items:
                item_data = {
                    "product_id": item.product_id,
                    "product_name": item.product_name if hasattr(item, 'product_name') else "Product",
                    "quantity": item.quantity,
                    "unit_price": item.unit_price if hasattr(item, 'unit_price') else 0,
                    "total_price": item.total_price if hasattr(item, 'total_price') else 0
                }
                
                # Try to get product details
                try:
                    product = await Product.find_one({"$or": [{"id": item.product_id}, {"_id": item.product_id}]})
                    if product:
                        item_data["product"] = {
                            "id": str(product.id),
                            "name": product.name,
                            "image_url": product.image_urls[0] if hasattr(product, 'image_urls') and product.image_urls and len(product.image_urls) > 0 else None
                        }
                except Exception as e:
                    logger.error(f"Error fetching product details: {e}")
                
                order_data["items"].append(item_data)
        
        # Add shipping address if available
        if hasattr(order, 'shipping_address') and order.shipping_address:
            order_data["shipping_address"] = {
                "street": order.shipping_address.street,
                "city": order.shipping_address.city,
                "state": order.shipping_address.state if hasattr(order.shipping_address, 'state') else None,
                "postal_code": order.shipping_address.postal_code if hasattr(order.shipping_address, 'postal_code') else None,
                "country": order.shipping_address.country,
                "phone": order.shipping_address.phone if hasattr(order.shipping_address, 'phone') else None
            }
        
        # Create a timeline based on order status
        timeline = []
        
        # Order placed (always included)
        timeline.append({
            "status": "Order Placed",
            "completed": True,
            "date": order.created_at.isoformat(),
            "description": f"Order #{order.order_no if hasattr(order, 'order_no') else order.id} has been placed successfully."
        })
        
        # Processing
        timeline.append({
            "status": "Processing",
            "completed": order.status in [OrderStatus.PROCESSING, OrderStatus.DELIVERING, OrderStatus.COMPLETED],
            "date": order.updated_at.isoformat() if order.status != OrderStatus.PENDING and order.updated_at else None,
            "description": "Your order is being processed and prepared for shipping."
        })
        
        # Delivering
        timeline.append({
            "status": "Out for Delivery",
            "completed": order.status in [OrderStatus.DELIVERING, OrderStatus.COMPLETED],
            "date": order.updated_at.isoformat() if order.status in [OrderStatus.DELIVERING, OrderStatus.COMPLETED] and order.updated_at else None,
            "description": "Your order is on its way to you."
        })
        
        # Delivered
        timeline.append({
            "status": "Delivered",
            "completed": order.status == OrderStatus.COMPLETED,
            "date": order.updated_at.isoformat() if order.status == OrderStatus.COMPLETED and order.updated_at else None,
            "description": "Your order has been delivered successfully."
        })
        
        # If cancelled, replace the timeline with a cancelled status
        if order.status == OrderStatus.CANCELLED:
            timeline = [{
                "status": "Order Placed",
                "completed": True,
                "date": order.created_at.isoformat(),
                "description": f"Order #{order.order_no if hasattr(order, 'order_no') else order.id} has been placed successfully."
            }, {
                "status": "Order Cancelled",
                "completed": True,
                "date": order.updated_at.isoformat() if order.updated_at else None,
                "description": "This order has been cancelled."
            }]
        
        order_data["timeline"] = timeline
        
        # Return JSON response with order data
        return JSONResponse({
            "success": True,
            "data": order_data
        })
    except Exception as e:
        logger.error(f"Error tracking order: {e}")
        return JSONResponse({
            "success": False,
            "error": f"An error occurred while tracking your order: {str(e)}"
        }, status_code=500)