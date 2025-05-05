from fastapi import APIRouter, Request, Depends, HTTPException, status, Body, Query, Path
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from app.database import get_db
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.models.user import User
from app.models.contact_info import ContactInfo, ContactMessage
from app.auth.jwt import get_current_active_admin
from app.admin.dashboard import templates, router
from app.utils.json import to_serializable_dict
from typing import Optional, List
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

# Contact Information Management Routes
@router.get("/contact-info", response_class=HTMLResponse)
async def contact_info_page(request: Request, current_user: User = Depends(get_current_active_admin)):
    """Admin page for managing contact information"""
    try:
        # Get current contact info
        contact_info = await ContactInfo.get_active()
        
        return templates.TemplateResponse(
            "dashboard/contact_info.html",
            {
                "request": request,
                "current_user": current_user,
                "contact_info": contact_info,
                "page_title": "Contact Information",
                "active_page": "contact_info"
            }
        )
    except Exception as e:
        logger.error(f"Error rendering contact info page: {str(e)}")
        return templates.TemplateResponse(
            "dashboard/contact_info.html",
            {
                "request": request,
                "current_user": current_user,
                "contact_info": None,
                "page_title": "Contact Information",
                "active_page": "contact_info",
                "error": "Failed to load contact information. Please try again."
            }
        )

@router.post("/api/contact-info/update")
async def update_contact_info(
    request: Request,
    address: str = Body(...),
    city: str = Body(...),
    country: str = Body(...),
    phone_numbers: List[str] = Body(...),
    email_addresses: List[str] = Body(...),
    monday_friday: str = Body(...),
    saturday: str = Body(...),
    sunday: str = Body(...),
    facebook: str = Body(default=""),
    twitter: str = Body(default=""),
    instagram: str = Body(default=""),
    contact_id: Optional[str] = Body(default=None),
    current_user: User = Depends(get_current_active_admin)
):
    """Update or create contact information"""
    try:
        # Check if we're updating existing info or creating new
        if contact_id:
            contact_info = await ContactInfo.find_one({"id": contact_id})
            if not contact_info:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content={"success": False, "error": "Contact information not found"}
                )
        else:
            # If creating new, first deactivate any existing active contact info
            existing_info = await ContactInfo.get_active()
            if existing_info:
                existing_info.is_active = False
                await existing_info.save()
            
            # Create new contact info
            contact_info = ContactInfo(
                address=address,
                city=city,
                country=country,
                phone_numbers=phone_numbers,
                email_addresses=email_addresses,
                business_hours={
                    "monday_friday": monday_friday,
                    "saturday": saturday,
                    "sunday": sunday
                },
                social_media={
                    "facebook": facebook,
                    "twitter": twitter,
                    "instagram": instagram
                }
            )
        
        # Update fields if we're updating existing info
        if contact_id:
            contact_info.address = address
            contact_info.city = city
            contact_info.country = country
            contact_info.phone_numbers = phone_numbers
            contact_info.email_addresses = email_addresses
            contact_info.business_hours = {
                "monday_friday": monday_friday,
                "saturday": saturday,
                "sunday": sunday
            }
            contact_info.social_media = {
                "facebook": facebook,
                "twitter": twitter,
                "instagram": instagram
            }
            contact_info.updated_at = datetime.utcnow()
        
        # Save to database
        await contact_info.save()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "message": "Contact information updated successfully",
                "data": to_serializable_dict(contact_info)
            }
        )
    except Exception as e:
        logger.error(f"Error updating contact info: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "Failed to update contact information"}
        )

# Contact Messages Management Routes
@router.get("/contact-messages", response_class=HTMLResponse)
async def contact_messages_page(
    request: Request, 
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_active_admin)
):
    """Admin page for viewing contact form messages"""
    try:
        # Calculate pagination
        skip = (page - 1) * limit
        
        # Get messages with pagination
        messages = await ContactMessage.find(skip=skip, limit=limit)
        total_messages = await ContactMessage.count()
        
        # Calculate total pages
        total_pages = (total_messages + limit - 1) // limit
        
        # Count unread messages
        unread_count = await ContactMessage.count({"is_read": False})
        
        return templates.TemplateResponse(
            "dashboard/contact_messages.html",
            {
                "request": request,
                "current_user": current_user,
                "messages": messages,
                "page": page,
                "limit": limit,
                "total_pages": total_pages,
                "total_messages": total_messages,
                "unread_count": unread_count,
                "page_title": "Contact Messages",
                "active_page": "contact_messages"
            }
        )
    except Exception as e:
        logger.error(f"Error rendering contact messages page: {str(e)}")
        return templates.TemplateResponse(
            "dashboard/contact_messages.html",
            {
                "request": request,
                "current_user": current_user,
                "messages": [],
                "page": 1,
                "limit": limit,
                "total_pages": 0,
                "total_messages": 0,
                "unread_count": 0,
                "page_title": "Contact Messages",
                "active_page": "contact_messages",
                "error": "Failed to load contact messages. Please try again."
            }
        )

@router.get("/contact-messages/{message_id}", response_class=HTMLResponse)
async def view_contact_message(
    request: Request,
    message_id: str = Path(...),
    current_user: User = Depends(get_current_active_admin)
):
    """View a single contact message"""
    try:
        # Get the message
        message = await ContactMessage.get_by_id(message_id)
        if not message:
            return RedirectResponse(
                url="/admin/contact-messages",
                status_code=status.HTTP_303_SEE_OTHER
            )
        
        # Mark as read if not already
        if not message.is_read:
            await message.mark_as_read()
        
        return templates.TemplateResponse(
            "dashboard/view_message.html",
            {
                "request": request,
                "current_user": current_user,
                "message": message,
                "page_title": f"Message from {message.name}",
                "active_page": "contact_messages"
            }
        )
    except Exception as e:
        logger.error(f"Error viewing contact message: {str(e)}")
        return RedirectResponse(
            url="/admin/contact-messages",
            status_code=status.HTTP_303_SEE_OTHER
        )

@router.post("/api/contact-messages/{message_id}/mark-read")
async def mark_message_read(
    request: Request,
    message_id: str = Path(...),
    current_user: User = Depends(get_current_active_admin)
):
    """Mark a message as read"""
    try:
        message = await ContactMessage.get_by_id(message_id)
        if not message:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"success": False, "error": "Message not found"}
            )
        
        await message.mark_as_read()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "message": "Message marked as read"
            }
        )
    except Exception as e:
        logger.error(f"Error marking message as read: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "Failed to mark message as read"}
        )

@router.delete("/api/contact-messages/{message_id}")
async def delete_message(
    request: Request,
    message_id: str = Path(...),
    current_user: User = Depends(get_current_active_admin)
):
    """Delete a contact message"""
    try:
        message = await ContactMessage.get_by_id(message_id)
        if not message:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"success": False, "error": "Message not found"}
            )
        
        await message.delete()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "message": "Message deleted successfully"
            }
        )
    except Exception as e:
        logger.error(f"Error deleting message: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "Failed to delete message"}
        )
