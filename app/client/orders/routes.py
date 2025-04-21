from fastapi import APIRouter, Request, Depends, HTTPException, status, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.database import get_db
from app.models.order import Order, OrderStatus, OrderItem, PaymentStatus
from app.models.user import User
from app.models.product import Product
from app.auth.jwt import get_current_user, get_current_user_optional
from app.client.orders import router, templates
from typing import Optional, List
from datetime import datetime, timedelta
import math
import uuid

@router.get("/my-orders", response_class=HTMLResponse)
async def get_client_orders(
  request: Request,
  page: int = Query(1, ge=1),
  page_size: int = Query(10, ge=5, le=100),
  current_user: User = Depends(get_current_user)
):
  """
  Retrieve all orders associated with the authenticated client with pagination.
  Renders a template with the list of orders.
  """
  # Calculate offset for pagination
  skip = (page - 1) * page_size
  
  # Get total count for pagination
  total_count = await Order.find({"user_id": str(current_user.id)}).count()
  
  # Calculate total pages
  total_pages = math.ceil(total_count / page_size)
  
  # Query orders with pagination
  orders = await Order.find({"user_id": str(current_user.id)}).sort("-created_at").skip(skip).limit(page_size).to_list()
  
  # For each order, fetch its order items and the associated products
  for order in orders:
    # Fetch order items
    order.order_items = await OrderItem.find({"order_id": str(order.id)}).to_list()
    
    # Fetch products for each order item
    for item in order.order_items:
      item.product = await Product.find_one({"id": item.product_id})
  
  return templates.TemplateResponse(
      "orders/my_orders.html", 
      {
          "request": request, 
          "orders": orders,
          "user": current_user,
          "pagination": {
              "current_page": page,
              "total_pages": total_pages,
              "has_next": page < total_pages,
              "has_prev": page > 1,
              "total_items": total_count
          }
      }
  )

@router.get("/orders/filter", response_class=HTMLResponse)
async def filter_client_orders(
  request: Request,
  status: Optional[str] = None,
  payment_status: Optional[str] = None,
  date_from: Optional[str] = None,
  date_to: Optional[str] = None,
  page: int = Query(1, ge=1),
  page_size: int = Query(10, ge=5, le=100),
  current_user: User = Depends(get_current_user)
):
  """
  Filter orders by status, payment status, and date range with pagination.
  """
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
  
  # Query orders with pagination
  orders = await Order.find(query).sort("-created_at").skip(skip).limit(page_size).to_list()
  
  # For each order, fetch its order items and the associated products
  for order in orders:
    # Fetch order items
    order.order_items = await OrderItem.find({"order_id": str(order.id)}).to_list()
    
    # Fetch products for each order item
    for item in order.order_items:
      item.product = await Product.find_one({"id": item.product_id})
  
  return templates.TemplateResponse(
      "orders/my_orders.html", 
      {
          "request": request, 
          "orders": orders,
          "user": current_user,
          "current_status": status,
          "current_payment_status": payment_status,
          "date_from": date_from,
          "date_to": date_to,
          "pagination": {
              "current_page": page,
              "total_pages": total_pages,
              "has_next": page < total_pages,
              "has_prev": page > 1,
              "total_items": total_count
          }
      }
  )

@router.get("/order/{order_id}", response_class=HTMLResponse)
async def get_order_details(
  request: Request,
  order_id: str,
  current_user: User = Depends(get_current_user)
):
  """
  Retrieve details of a specific order by ID.
  """
  # Find the order
  order = await Order.find_one({"id": order_id, "user_id": str(current_user.id)})
  
  if not order:
      raise HTTPException(status_code=404, detail="Order not found")
  
  # Get order items
  order.order_items = await OrderItem.find({"order_id": order_id}).to_list()
  
  # Get products for each order item
  for item in order.order_items:
      item.product = await Product.find_one({"id": item.product_id})
      
      # If product exists, increment its view_count
      if item.product:
          # Initialize view_count if it doesn't exist
          if not hasattr(item.product, 'view_count') or item.product.view_count is None:
              item.product.view_count = 0
          
          # Increment view count (viewing product in order details also counts as a view)
          item.product.view_count += 1
          await item.product.save()
  
  # Get the address
  order.address = await Order.find_one({"id": order.address_id}) if order.address_id else None
  
  return templates.TemplateResponse(
      "orders/order_view.html", 
      {
          "request": request, 
          "order": order, 
          "user": current_user
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
  # Find the order
  order = await Order.find_one({"id": order_id, "user_id": str(current_user.id)})
  
  if not order:
      raise HTTPException(status_code=404, detail="Order not found")
  
  # Get order items
  order.order_items = await OrderItem.find({"order_id": order_id}).to_list()
  
  # Get products for each order item
  for item in order.order_items:
      item.product = await Product.find_one({"id": item.product_id})
  
  # Get the address
  order.address = await Order.find_one({"id": order.address_id}) if order.address_id else None
  
  # Create a timeline based on order status
  timeline = []
  
  # Order placed (always included)
  timeline.append({
      "status": "Order Placed",
      "completed": True,
      "date": order.created_at,
      "description": f"Order #{order.order_no} has been placed successfully."
  })
  
  # Processing
  timeline.append({
      "status": "Processing",
      "completed": order.status in [OrderStatus.PROCESSING.value, OrderStatus.DELIVERING.value, OrderStatus.DELIVERED.value],
      "date": order.updated_at if order.status != OrderStatus.PENDING.value else None,
      "description": "Your order is being processed and prepared for shipping."
  })
  
  # Delivering
  timeline.append({
      "status": "Out for Delivery",
      "completed": order.status in [OrderStatus.DELIVERING.value, OrderStatus.DELIVERED.value],
      "date": order.updated_at if order.status in [OrderStatus.DELIVERING.value, OrderStatus.DELIVERED.value] else None,
      "description": "Your order is on its way to you."
  })
  
  # Delivered
  timeline.append({
      "status": "Delivered",
      "completed": order.status == OrderStatus.DELIVERED.value,
      "date": order.updated_at if order.status == OrderStatus.DELIVERED.value else None,
      "description": "Your order has been delivered successfully."
  })
  
  # If cancelled, replace the timeline with a cancelled status
  if order.status == OrderStatus.CANCELLED.value:
      timeline = [{
          "status": "Order Placed",
          "completed": True,
          "date": order.created_at,
          "description": f"Order #{order.order_no} has been placed successfully."
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
          "user": current_user
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
  # Find the order
  order = await Order.find_one({"id": order_id, "user_id": str(current_user.id)})
  
  if not order:
      raise HTTPException(
          status_code=status.HTTP_404_NOT_FOUND, 
          detail="Order not found"
      )
  
  # Check if order can be cancelled
  if order.status != OrderStatus.PENDING.value:
      # Get order items and products for the error template
      order.order_items = await OrderItem.find({"order_id": order_id}).to_list()
      
      for item in order.order_items:
          item.product = await Product.find_one({"id": item.product_id})
      
      # Return to order page with error
      return templates.TemplateResponse(
          "orders/order_view.html", 
          {
              "request": request, 
              "order": order, 
              "user": current_user,
              "error": "Only pending orders can be cancelled"
          },
          status_code=400
      )
  
  # Update order status to cancelled
  order.status = OrderStatus.CANCELLED.value
  order.updated_at = datetime.utcnow()
  await order.save()
  
  # Redirect back to order page
  return RedirectResponse(
      url=f"/order/{order_id}", 
      status_code=status.HTTP_303_SEE_OTHER
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
  # Find the order
  order = await Order.find_one({"id": order_id, "user_id": str(current_user.id)})
  
  if not order:
      raise HTTPException(
          status_code=status.HTTP_404_NOT_FOUND, 
          detail="Order not found"
      )
  
  # Check if order is eligible for refund (must be delivered and not already refunded)
  if order.status != OrderStatus.DELIVERED.value or order.payment_status == PaymentStatus.REFUNDED.value:
      # Get order items and products for the error template
      order.order_items = await OrderItem.find({"order_id": order_id}).to_list()
      
      for item in order.order_items:
          item.product = await Product.find_one({"id": item.product_id})
      
      return templates.TemplateResponse(
          "orders/order_view.html", 
          {
              "request": request, 
              "order": order, 
              "user": current_user,
              "error": "This order is not eligible for a refund"
          },
          status_code=400
      )
  
  # Update the payment status to REFUNDED
  order.payment_status = PaymentStatus.REFUNDED.value
  order.updated_at = datetime.utcnow()
  await order.save()
  
  # You might want to store the refund reason in a separate table
  # For simplicity, we'll just log it
  print(f"Refund requested for order {order_id} with reason: {reason}")
  
  # Get order items and products for the success template
  order.order_items = await OrderItem.find({"order_id": order_id}).to_list()
  
  for item in order.order_items:
      item.product = await Product.find_one({"id": item.product_id})
  
  # Return success template
  return templates.TemplateResponse(
      "orders/order_view.html", 
      {
          "request": request, 
          "order": order, 
          "user": current_user,
          "success": "Your refund request has been submitted successfully"
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
          "order_no": order.order_no,
          "total_amount": order.total_amount,
          "amount_paid": order.amount_paid,
          "status": order.status,
          "payment_status": order.payment_status,
          "created_at": order.created_at.isoformat(),
          "updated_at": order.updated_at.isoformat()
      })
  
  return JSONResponse({
      "orders": order_list,
      "page": page,
      "page_size": page_size,
      "total_count": len(order_list)
  })

@router.get("/track", response_class=HTMLResponse)
async def track_order_form(request: Request):
    """
    Display a form for tracking orders by order number.
    """
    return templates.TemplateResponse(
        "orders/track_order_form.html", 
        {"request": request}
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
    # Validate input - make sure it's a valid order number format
    if not order_no or len(order_no) < 3:
        return templates.TemplateResponse(
            "orders/track_order_form.html",
            {
                "request": request,
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
                "error": "This order belongs to a registered user. Please log in to view details.",
                "order_no": order_no
            }
        )
    
    # If found, redirect to the order tracking page
    return RedirectResponse(url=f"/track-order-by-number/{order.order_no}", status_code=status.HTTP_303_SEE_OTHER)

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
    
    # Get order items
    order.order_items = await OrderItem.find({"order_id": str(order.id)}).to_list()
    
    # Get products for each order item
    for item in order.order_items:
        item.product = await Product.find_one({"id": item.product_id})
    
    # Get the address
    order.address = await Order.find_one({"id": order.address_id}) if order.address_id else None
    
    # Create a timeline based on order status
    timeline = []
    
    # Order placed (always included)
    timeline.append({
        "status": "Order Placed",
        "completed": True,
        "date": order.created_at,
        "description": f"Order #{order.order_no} has been placed successfully."
    })
    
    # Processing
    timeline.append({
        "status": "Processing",
        "completed": order.status in [OrderStatus.PROCESSING.value, OrderStatus.DELIVERING.value, OrderStatus.DELIVERED.value],
        "date": order.updated_at if order.status != OrderStatus.PENDING.value else None,
        "description": "Your order is being processed and prepared for shipping."
    })
    
    # Delivering
    timeline.append({
        "status": "Out for Delivery",
        "completed": order.status in [OrderStatus.DELIVERING.value, OrderStatus.DELIVERED.value],
        "date": order.updated_at if order.status in [OrderStatus.DELIVERING.value, OrderStatus.DELIVERED.value] else None,
        "description": "Your order is on its way to you."
    })
    
    # Delivered
    timeline.append({
        "status": "Delivered",
        "completed": order.status == OrderStatus.DELIVERED.value,
        "date": order.updated_at if order.status == OrderStatus.DELIVERED.value else None,
        "description": "Your order has been delivered successfully."
    })
    
    # If cancelled, replace the timeline with a cancelled status
    if order.status == OrderStatus.CANCELLED.value:
        timeline = [{
            "status": "Order Placed",
            "completed": True,
            "date": order.created_at,
            "description": f"Order #{order.order_no} has been placed successfully."
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
            "user": current_user
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
    
    # Get order items
    order.order_items = await OrderItem.find({"order_id": str(order.id)}).to_list()
    
    # Get products for each order item
    for item in order.order_items:
        item.product = await Product.find_one({"id": item.product_id})
        
        # Increment view count for each product in the order
        if item.product:
            # Initialize view_count if it doesn't exist
            if not hasattr(item.product, 'view_count') or item.product.view_count is None:
                item.product.view_count = 0
            
            # Increment view count
            item.product.view_count += 1
            await item.product.save()
    
    # Get the address
    order.address = await Order.find_one({"id": order.address_id}) if order.address_id else None
    
    # For guests, render the order view directly
    return templates.TemplateResponse(
        "checkout/order_view.html", 
        {
            "request": request, 
            "order": order,
            "user": current_user
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
    # Find the order
    order = await Order.find_one({"id": order_id, "user_id": str(current_user.id)})
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    # Only allow closing orders that are in "DELIVERED" status
    if order.status != OrderStatus.DELIVERED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only delivered orders can be marked as completed"
        )
    
    # Update the order status to COMPLETED
    order.status = OrderStatus.COMPLETED.value
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

