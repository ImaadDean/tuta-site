from fastapi import APIRouter, Request, Depends, HTTPException, status, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from typing import Optional, List
from app.models.contact_info import ContactMessage, ContactInfo
from app.models.user import User
from app.auth.jwt import get_current_active_admin
from app.admin.contact import router, templates
from app.database import get_db
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

@router.get("/", response_class=HTMLResponse)
async def list_contact_messages(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=5, le=50),
    is_read: Optional[bool] = None,
    is_replied: Optional[bool] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_active_admin)
):
    """
    List all contact messages with filtering and pagination
    """
    try:
        # Build the query
        query = {}

        # Apply read/unread filter
        if is_read is not None:
            query["is_read"] = is_read

        # Apply replied/not replied filter
        if is_replied is not None:
            query["is_replied"] = is_replied

        # Apply search filter if provided
        if search:
            # Search in subject, message, and user info
            query["$or"] = [
                {"subject": {"$regex": search, "$options": "i"}},
                {"message": {"$regex": search, "$options": "i"}},
                {"user_info.name": {"$regex": search, "$options": "i"}},
                {"user_info.email": {"$regex": search, "$options": "i"}}
            ]

        # Calculate pagination
        skip = (page - 1) * page_size

        # Get total count for pagination
        total_count = await ContactMessage.find(query).count()
        total_pages = (total_count + page_size - 1) // page_size

        # Get messages with pagination and sorting
        messages = await ContactMessage.find(query).sort([("created_at", -1)]).skip(skip).limit(page_size).to_list()

        # Get unread count for badge
        unread_count = await ContactMessage.find({"is_read": False}).count()

        return templates.TemplateResponse(
            "contact/list.html",
            {
                "request": request,
                "user": current_user,
                "messages": messages,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "total_count": total_count,
                "is_read": is_read,
                "is_replied": is_replied,
                "search": search,
                "unread_count": unread_count
            }
        )
    except Exception as e:
        logger.error(f"Error listing contact messages: {str(e)}")
        # Return the template with error message
        return templates.TemplateResponse(
            "contact/list.html",
            {
                "request": request,
                "user": current_user,
                "messages": [],
                "page": 1,
                "page_size": page_size,
                "total_pages": 0,
                "total_count": 0,
                "is_read": is_read,
                "is_replied": is_replied,
                "search": search,
                "unread_count": 0,
                "error": f"Could not list contact messages: {str(e)}"
            }
        )

@router.get("/message/{message_id}", response_class=HTMLResponse)
async def view_contact_message(
    request: Request,
    message_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    View a single contact message
    """
    try:
        # Get the message
        message = await ContactMessage.get_by_id(message_id)

        if not message:
            # If message not found, redirect to list with error message
            return RedirectResponse(
                url=f"/admin/contact/?error=Message with ID {message_id} not found",
                status_code=303
            )

        # Mark as read if not already
        if not message.is_read:
            message.is_read = True
            await message.save()

        # Get user information if available
        user_info = None
        if message.user_id:
            user_info = await User.find_one({"id": message.user_id})

        return templates.TemplateResponse(
            "contact/view.html",
            {
                "request": request,
                "user": current_user,
                "message": message,
                "user_info": user_info
            }
        )
    except Exception as e:
        logger.error(f"Error viewing contact message: {str(e)}")
        # Redirect to list with error message
        return RedirectResponse(
            url=f"/admin/contact/?error=Error viewing message: {str(e)}",
            status_code=303
        )

@router.get("/settings", response_class=HTMLResponse)
async def contact_settings(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Manage contact information settings
    """
    try:
        # Get current contact information
        contact_info = await ContactInfo.get_active()

        return templates.TemplateResponse(
            "contact/settings.html",
            {
                "request": request,
                "user": current_user,
                "contact_info": contact_info
            }
        )
    except Exception as e:
        logger.error(f"Error loading contact settings: {str(e)}")
        # Redirect to list with error message
        return RedirectResponse(
            url=f"/admin/contact/?error=Error loading contact settings: {str(e)}",
            status_code=303
        )
