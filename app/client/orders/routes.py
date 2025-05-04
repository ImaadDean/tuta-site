from fastapi import APIRouter, Request, Depends, HTTPException, status, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.database import get_db
from app.models.order import Order, OrderStatus, OrderItem, PaymentStatus
from app.models.user import User
from app.models.product import Product
from app.auth.jwt import get_current_user, get_current_active_client, get_current_user_optional
from app.client.orders import router, templates
from typing import Optional, List
from datetime import datetime, timedelta
import math
import uuid
import logging

# Set up logger
logger = logging.getLogger(__name__)

# @router.get("/my-orders", response_class=HTMLResponse)
# async def get_client_orders(
#     request: Request,
#     page: int = Query(1, ge=1),
#     page_size: int = Query(10, ge=5, le=100),
#     current_user: User = Depends(get_current_user)
# ):
#     try:
#         skip = (page - 1) * page_size

#         total_count = await Order.find({"user_id": str(current_user.id)}).count()
#         total_pages = math.ceil(total_count / page_size)

#         # Get raw orders from MongoDB
#         db = Order.get_motor_collection()
#         raw_orders = await db.find({"user_id": str(current_user.id)}).sort("created_at", -1).skip(skip).limit(page_size).to_list(length=None)

#         logger.info(f"Found {len(raw_orders)} raw orders for user {current_user.id}")

#         # Process orders for template
#         orders = []
#         for raw_order in raw_orders:
#             try:
#                 # Create an Order object from the raw MongoDB document
#                 order = Order.parse_obj(raw_order)
                
#                 # Ensure order has an order_no
#                 if not hasattr(order, "order_no") or not order.order_no:
#                     order.order_no = str(order.id)
                
#                 # Add the order to our list
#                 orders.append(order)
                
#                 logger.info(f"Successfully processed order {order.order_no}")
#             except Exception as e:
#                 logger.error(f"Error processing order: {e}")
#                 continue

#         return templates.TemplateResponse(
#             "orders/my_orders.html",
#             {
#                 "request": request,
#                 "orders": orders,
#                 "current_user": current_user,
#                 "pagination": {
#                     "current_page": page,
#                     "total_pages": total_pages,
#                     "has_next": page < total_pages,
#                     "has_prev": page > 1,
#                     "total_items": total_count
#                 }
#             }
#         )
#     except Exception as e:
#         logger.error(f"Error retrieving orders: {e}")
#         return templates.TemplateResponse(
#             "orders/error.html",
#             {
#                 "request": request,
#                 "current_user": current_user,
#                 "error": f"An error occurred while retrieving your orders: {str(e)}"
#             }
#         )


@router.get("/order/{order_id}", response_class=HTMLResponse)
async def get_order_details(
  request: Request,
  order_id: str,
  current_user: User = Depends(get_current_user)
):
  """
  Render the order details page. The actual order data will be fetched client-side via API.
  """
  try:
    # Just render the template - data will be fetched via API
    return templates.TemplateResponse(
        "orders/order_view.html", 
        {
            "request": request,
            "order_id": order_id,
            "current_user": current_user
        }
    )
  except Exception as e:
    logger.error(f"Error rendering order details page: {e}")
    return templates.TemplateResponse(
        "orders/error.html",
        {
            "request": request,
            "current_user": current_user,
            "error": f"An error occurred while loading the order details page: {str(e)}"
        }
    )

@router.get("/my-orders", response_class=HTMLResponse)
async def get_client_orders_api(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Render the orders page that uses the API endpoints to fetch and display orders.
    This version uses client-side JavaScript to fetch data from the API.
    """
    try:
        return templates.TemplateResponse(
            "orders/my_orders.html",
            {
                "request": request,
                "current_user": current_user
            }
        )
    except Exception as e:
        logger.error(f"Error rendering API orders page: {e}")
        return templates.TemplateResponse(
            "orders/error.html",
            {
                "request": request,
                "current_user": current_user,
                "error": f"An error occurred while loading the orders page: {str(e)}"
            }
        )



@router.get("/track", response_class=HTMLResponse)
async def track_order_form(
    request: Request, 
    current_user: Optional[User] = Depends(get_current_active_client)
):
    """
    Display a unified form for tracking orders by order number.
    """
    return templates.TemplateResponse(
        "orders/track_order.html", 
        {
            "request": request, 
            "current_user": current_user
        }
    )

@router.get("/track-order/{order_id}", response_class=HTMLResponse)
async def track_order(
  request: Request,
  order_id: str,
  current_user: User = Depends(get_current_user)
):
  """
  Track the status of a specific order with detailed timeline.
  """
  try:
    # Find the order
    order = await Order.find_one({"id": order_id, "user_id": str(current_user.id)})
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Use the items field directly
    order.order_items = order.items if hasattr(order, 'items') else []
    
    # Get products for each order item
    for item in order.order_items:
        product_id = item.product_id if hasattr(item, 'product_id') else None
        if product_id:
            item.product = await Product.find_one({"id": product_id})
    
    # Get the address from the shipping_address field
    order.address = order.shipping_address if hasattr(order, 'shipping_address') else None
    
    # Create a timeline based on order status
    timeline = []
    
    # Order placed (always included)
    timeline.append({
        "status": "Order Placed",
        "completed": True,
        "date": order.created_at,
        "description": f"Order #{order.order_no if hasattr(order, 'order_no') else order.id} has been placed successfully."
    })
    
    # Processing
    timeline.append({
        "status": "Processing",
        "completed": order.status in [OrderStatus.PROCESSING, OrderStatus.DELIVERING, OrderStatus.COMPLETED],
        "date": order.updated_at if order.status != OrderStatus.PENDING else None,
        "description": "Your order is being processed and prepared for shipping."
    })
    
    # Delivering
    timeline.append({
        "status": "Out for Delivery",
        "completed": order.status in [OrderStatus.DELIVERING, OrderStatus.COMPLETED],
        "date": order.updated_at if order.status in [OrderStatus.DELIVERING, OrderStatus.COMPLETED] else None,
        "description": "Your order is on its way to you."
    })
    
    # Delivered
    timeline.append({
        "status": "Delivered",
        "completed": order.status == OrderStatus.COMPLETED,
        "date": order.updated_at if order.status == OrderStatus.COMPLETED else None,
        "description": "Your order has been delivered successfully."
    })
    
    # If cancelled, replace the timeline with a cancelled status
    if order.status == OrderStatus.CANCELLED:
        timeline = [{
            "status": "Order Placed",
            "completed": True,
            "date": order.created_at,
            "description": f"Order #{order.order_no if hasattr(order, 'order_no') else order.id} has been placed successfully."
        }, {
            "status": "Order Cancelled",
            "completed": True,
            "date": order.updated_at,
            "description": "This order has been cancelled."
        }]
    
    return templates.TemplateResponse(
        "orders/track_order.html", 
        {
            "request": request, 
            "order": order,
            "timeline": timeline,
            "current_user": current_user
        }
    )
  except HTTPException:
    # Re-raise HTTP exceptions
    raise
  except Exception as e:
    logger.error(f"Error tracking order: {e}")
    return templates.TemplateResponse(
        "orders/error.html",
        {
            "request": request,
            "current_user": current_user,
            "error": f"An error occurred while tracking your order: {str(e)}"
        }
    )

@router.post("/cancel-order/{order_id}")
async def cancel_order(
  order_id: str,
  request: Request,
  current_user: User = Depends(get_current_user)
):
  """
  Cancel an existing order if its status is 'pending'.
  Redirects back to the order details page after processing.
  """
  try:
    # Find the order
    order = await Order.find_one({"id": order_id, "user_id": str(current_user.id)})
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Order not found"
        )
    
    # Check if order can be cancelled
    if order.status != OrderStatus.PENDING:
        # Use the items field directly
        order.order_items = order.items if hasattr(order, 'items') else []
        
        for item in order.order_items:
            product_id = item.product_id if hasattr(item, 'product_id') else None
            if product_id:
                item.product = await Product.find_one({"id": product_id})
        
        # Return to order page with error
        return templates.TemplateResponse(
            "orders/order_view.html", 
            {
                "request": request, 
                "order": order, 
                "current_user": current_user,
                "error": "Only pending orders can be cancelled"
            },
            status_code=400
        )
    
    # Update order status to cancelled
    order.status = OrderStatus.CANCELLED
    order.updated_at = datetime.utcnow()
    await order.save()
    
    # Redirect back to order page
    return RedirectResponse(
        url=f"/order/{order_id}", 
        status_code=status.HTTP_303_SEE_OTHER
    )
  except HTTPException:
    # Re-raise HTTP exceptions
    raise
  except Exception as e:
    logger.error(f"Error cancelling order: {e}")
    return templates.TemplateResponse(
        "orders/error.html",
        {
            "request": request,
            "current_user": current_user,
            "error": f"An error occurred while cancelling your order: {str(e)}"
        }
    )

@router.post("/request-refund/{order_id}")
async def request_refund(
  order_id: str,
  request: Request,
  reason: str = Form(...),
  current_user: User = Depends(get_current_user)
):
  """
  Request a refund for a delivered order.
  """
  try:
    # Find the order
    order = await Order.find_one({"id": order_id, "user_id": str(current_user.id)})
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Order not found"
        )
    
    # Check if order is eligible for refund (must be delivered and not already refunded)
    if order.status != OrderStatus.COMPLETED or order.payment_status == PaymentStatus.REFUNDED:
        # Use the items field directly
        order.order_items = order.items if hasattr(order, 'items') else []
        
        for item in order.order_items:
            product_id = item.product_id if hasattr(item, 'product_id') else None
            if product_id:
                item.product = await Product.find_one({"id": product_id})
        
        return templates.TemplateResponse(
            "orders/order_view.html", 
            {
                "request": request, 
                "order": order, 
                "current_user": current_user,
                "error": "This order is not eligible for a refund"
            },
            status_code=400
        )
    
    # Update the payment status to REFUNDED
    order.payment_status = PaymentStatus.REFUNDED
    order.updated_at = datetime.utcnow()
    await order.save()
    
    # You might want to store the refund reason in a separate table
    # For simplicity, we'll just log it
    logger.info(f"Refund requested for order {order_id} with reason: {reason}")
    
    # Use the items field directly
    order.order_items = order.items if hasattr(order, 'items') else []
    
    for item in order.order_items:
        product_id = item.product_id if hasattr(item, 'product_id') else None
        if product_id:
            item.product = await Product.find_one({"id": product_id})
    
    # Return success template
    return templates.TemplateResponse(
        "orders/order_view.html", 
        {
            "request": request, 
            "order": order, 
            "current_user": current_user,
            "success": "Your refund request has been submitted successfully"
        }
    )
  except HTTPException:
    # Re-raise HTTP exceptions
    raise
  except Exception as e:
    logger.error(f"Error requesting refund: {e}")
    return templates.TemplateResponse(
        "orders/error.html",
        {
            "request": request,
            "current_user": current_user,
            "error": f"An error occurred while requesting a refund: {str(e)}"
        }
    )

@router.get("/api/orders", response_model=List[dict])
async def get_orders_api(
  status: Optional[str] = None,
  payment_status: Optional[str] = None,
  page: int = Query(1, ge=1),
  page_size: int = Query(10, ge=5, le=100),
  current_user: User = Depends(get_current_user)
):
  """
  API endpoint to get orders for the current user.
  Useful for AJAX requests and mobile apps.
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
    
    # Calculate offset for pagination
    skip = (page - 1) * page_size
    
    # Execute query
    orders = await Order.find(query).sort("-created_at").skip(skip).limit(page_size).to_list()
    
    # Format orders for API response
    order_list = []
    for order in orders:
        order_list.append({
            "id": str(order.id),
            "order_no": order.order_no if hasattr(order, 'order_no') else str(order.id),
            "total_amount": order.total_amount,
            "amount_paid": order.amount_paid if hasattr(order, 'amount_paid') else 0,
            "status": order.status,
            "payment_status": order.payment_status,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat() if order.updated_at else None
        })
    
    return JSONResponse({
        "orders": order_list,
        "page": page,
        "page_size": page_size,
        "total_count": len(order_list)
    })
  except Exception as e:
    logger.error(f"Error retrieving orders API: {e}")
    return JSONResponse({
        "error": f"An error occurred while retrieving orders: {str(e)}"
    }, status_code=500)

@router.get("/track", response_class=HTMLResponse)
async def track_order_form(request: Request, current_user: Optional[User] = Depends(get_current_user_optional)):
    """
    Display a form for tracking orders by order number.
    """
    return templates.TemplateResponse(
        "orders/track_order_form.html", 
        {"request": request, "current_user": current_user}
    )

@router.post("/track", response_class=HTMLResponse)
async def track_order_by_number(
    request: Request,
    order_no: str = Form(...),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Track an order by its order number.
    This works for both logged-in users and guests.
    """
    try:
      # Validate input - make sure it's a valid order number format
      if not order_no or len(order_no) < 3:
          return templates.TemplateResponse(
              "orders/track_order_form.html",
              {
                  "request": request,
                  "current_user": current_user,
                  "error": "Please enter a valid order number",
                  "order_no": order_no
              }
          )
      
      # Build query to find the order
      query = {"order_no": order_no.upper()}
      
      # For logged-in users, we show only their orders
      if current_user:
          query["user_id"] = str(current_user.id)
      
      # Find the order
      order = await Order.find_one(query)
      
      if not order:
          return templates.TemplateResponse(
              "orders/track_order_form.html",
              {
                  "request": request,
                  "current_user": current_user,
                  "error": "Order not found. Please check the order number and try again.",
                  "order_no": order_no
              }
          )
      
      # Additional security check for guest users - if order belongs to a registered user, don't show details
      if not current_user and order.user_id:
          return templates.TemplateResponse(
              "orders/track_order_form.html",
              {
                  "request": request,
                  "current_user": current_user,
                  "error": "This order belongs to a registered user. Please log in to view details.",
                  "order_no": order_no
              }
          )
      
      # If found, redirect to the order tracking page
      return RedirectResponse(url=f"/track-order-by-number/{order.order_no if hasattr(order, 'order_no') else order.id}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
      logger.error(f"Error tracking order by number: {e}")
      return templates.TemplateResponse(
          "orders/track_order_form.html",
          {
              "request": request,
              "current_user": current_user,
              "error": f"An error occurred while tracking your order: {str(e)}",
              "order_no": order_no
          }
      )

@router.get("/track-order-by-number/{order_no}", response_class=HTMLResponse)
async def track_order_by_number_get(
    request: Request,
    order_no: str,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Track the status of a specific order with detailed timeline using the order number.
    Works for both logged-in users and guests.
    """
    try:
      # Build query to find the order
      query = {"order_no": order_no.upper()}
      
      # For logged-in users, we show only their orders
      if current_user:
          query["user_id"] = str(current_user.id)
      
      # Find the order
      order = await Order.find_one(query)
      
      if not order:
          raise HTTPException(status_code=404, detail="Order not found")
      
      # Additional security check for guest users - if order belongs to a registered user, don't show details
      if not current_user and order.user_id:
          raise HTTPException(
              status_code=status.HTTP_403_FORBIDDEN,
              detail="This order belongs to a registered user. Please log in to view details."
          )
      
      # Create a dictionary to store products by their ID
      products = {}
      
      # Fetch products for each order item
      for item in order.items:
          product_id = item.product_id
          if product_id and product_id not in products:
              product = await Product.find_one({"id": product_id})
              if product:
                  products[product_id] = product
      
      # Create a timeline based on order status
      timeline = []
      
      # Order placed (always included)
      timeline.append({
          "status": "Order Placed",
          "completed": True,
          "date": order.created_at,
          "description": f"Order #{order.order_no if hasattr(order, 'order_no') else order.id} has been placed successfully."
      })
      
      # Processing
      timeline.append({
          "status": "Processing",
          "completed": order.status in [OrderStatus.PROCESSING, OrderStatus.DELIVERING, OrderStatus.COMPLETED],
          "date": order.updated_at if order.status != OrderStatus.PENDING else None,
          "description": "Your order is being processed and prepared for shipping."
      })
      
      # Delivering
      timeline.append({
          "status": "Out for Delivery",
          "completed": order.status in [OrderStatus.DELIVERING, OrderStatus.COMPLETED],
          "date": order.updated_at if order.status in [OrderStatus.DELIVERING, OrderStatus.COMPLETED] else None,
          "description": "Your order is on its way to you."
      })
      
      # Delivered
      timeline.append({
          "status": "Delivered",
          "completed": order.status == OrderStatus.COMPLETED,
          "date": order.updated_at if order.status == OrderStatus.COMPLETED else None,
          "description": "Your order has been delivered successfully."
      })
      
      # If cancelled, replace the timeline with a cancelled status
      if order.status == OrderStatus.CANCELLED:
          timeline = [{
              "status": "Order Placed",
              "completed": True,
              "date": order.created_at,
              "description": f"Order #{order.order_no if hasattr(order, 'order_no') else order.id} has been placed successfully."
          }, {
              "status": "Order Cancelled",
              "completed": True,
              "date": order.updated_at,
              "description": "This order has been cancelled."
          }]
      
      return templates.TemplateResponse(
          "orders/track_order.html", 
          {
              "request": request, 
              "order": order,
              "products": products,  # Pass the products dictionary
              "timeline": timeline,
              "current_user": current_user
          }
      )
    except HTTPException:
      # Re-raise HTTP exceptions
      raise
    except Exception as e:
      logger.error(f"Error tracking order by number: {e}")
      return templates.TemplateResponse(
          "orders/error.html",
          {
              "request": request,
              "current_user": current_user,
              "error": f"An error occurred while tracking your order: {str(e)}"
          }
      )

@router.get("/order/by-number/{order_no}", response_class=HTMLResponse)
async def view_order_by_number(
    request: Request,
    order_no: str,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    View order details by order number.
    Works for both logged-in users and guests.
    """
    try:
      # Find the order by order number
      query = {"order_no": order_no.upper()}
      
      # For logged-in users, we show only their orders
      if current_user:
          query["user_id"] = str(current_user.id)
      
      # Find the order
      order = await Order.find_one(query)
      
      if not order:
          raise HTTPException(
              status_code=status.HTTP_404_NOT_FOUND,
              detail="Order not found. Please check the order number."
          )
      
      # Additional security check for guest users - if order belongs to a registered user, don't show details
      if not current_user and order.user_id:
          raise HTTPException(
              status_code=status.HTTP_403_FORBIDDEN,
              detail="This order belongs to a registered user. Please log in to view details."
          )
      
      # For logged-in users, redirect to the standard order details page
      if current_user:
          return RedirectResponse(url=f"/order/{order.id}", status_code=status.HTTP_303_SEE_OTHER)
      
      # Use the items field directly
      order.order_items = order.items if hasattr(order, 'items') else []
      
      # Get products for each order item
      for item in order.order_items:
          product_id = item.product_id if hasattr(item, 'product_id') else None
          if product_id:
              item.product = await Product.find_one({"id": product_id})
              
              # Increment view count for each product in the order
              if item.product:
                  # Initialize view_count if it doesn't exist
                  if not hasattr(item.product, 'view_count') or item.product.view_count is None:
                      item.product.view_count = 0
                  
                  # Increment view count
                  item.product.view_count += 1
                  await item.product.save()
      
      # Get the address from the shipping_address field
      order.address = order.shipping_address if hasattr(order, 'shipping_address') else None
      
      # For guests, render the order view directly
      return templates.TemplateResponse(
          "checkout/order_view.html", 
          {
              "request": request, 
              "order": order,
              "current_user": current_user
          }
      )
    except HTTPException:
      # Re-raise HTTP exceptions
      raise
    except Exception as e:
      logger.error(f"Error viewing order by number: {e}")
      return templates.TemplateResponse(
          "orders/error.html",
          {
              "request": request,
              "current_user": current_user,
              "error": f"An error occurred while viewing your order: {str(e)}"
          }
      )

@router.post("/close-order/{order_id}")
async def close_order(
    order_id: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Mark an order as closed/completed by the customer.
    This is used when a customer is satisfied with the order and wants to mark it as complete.
    """
    try:
      # Find the order
      order = await Order.find_one({"id": order_id, "user_id": str(current_user.id)})
      
      if not order:
          raise HTTPException(
              status_code=status.HTTP_404_NOT_FOUND,
              detail="Order not found"
          )
      
      # Only allow closing orders that are in "DELIVERED" status
      if order.status != OrderStatus.DELIVERED:
          raise HTTPException(
              status_code=status.HTTP_400_BAD_REQUEST,
              detail="Only delivered orders can be marked as completed"
          )
      
      # Update the order status to COMPLETED
      order.status = OrderStatus.COMPLETED
      order.updated_at = datetime.utcnow()
      await order.save()
      
      try:
          # Check if it's an AJAX request
          if "application/json" in request.headers.get("accept", ""):
              return JSONResponse({
                  "success": True,
                  "message": "Order has been marked as completed.",
                  "status": order.status
              })
          
          # For regular form submission, redirect back to the order details
          return RedirectResponse(
              url=f"/order/{order_id}?message=Order+has+been+marked+as+completed",
              status_code=status.HTTP_303_SEE_OTHER
          )
          
      except Exception as e:
          raise HTTPException(
              status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
              detail=f"An error occurred while updating the order: {str(e)}"
          )
    except HTTPException:
      # Re-raise HTTP exceptions
      raise
    except Exception as e:
      logger.error(f"Error closing order: {e}")
      return templates.TemplateResponse(
          "orders/error.html",
          {
              "request": request,
              "current_user": current_user,
              "error": f"An error occurred while closing your order: {str(e)}"
          }
      )
