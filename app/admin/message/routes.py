from fastapi import APIRouter, Request, Depends, HTTPException, status, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from typing import Optional, List
from app.models.message import Message
from app.models.user import User
from app.auth.jwt import get_current_active_admin
from app.admin.message import router, templates
from app.database import get_db
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

@router.get("/", response_class=HTMLResponse)
async def list_messages(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=5, le=50),
    is_read: Optional[bool] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_active_admin)
):
    """
    List all user messages with filtering and pagination
    """
    try:
        # Build the query
        query = {}

        # Apply read/unread filter
        if is_read is not None:
            query["is_read"] = is_read

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
        total_count = await Message.find(query).count()
        total_pages = (total_count + page_size - 1) // page_size

        # Get messages with pagination and sorting
        messages = await Message.find(query).sort([("created_at", -1)]).skip(skip).limit(page_size).to_list()

        # Get unread count for badge
        unread_count = await Message.find({"is_read": False}).count()

        return templates.TemplateResponse(
            "message/list.html",
            {
                "request": request,
                "user": current_user,
                "messages": messages,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "total_count": total_count,
                "is_read": is_read,
                "search": search,
                "unread_count": unread_count
            }
        )
    except Exception as e:
        logger.error(f"Error listing messages: {str(e)}")
        # Return the template with error message
        return templates.TemplateResponse(
            "message/list.html",
            {
                "request": request,
                "user": current_user,
                "messages": [],
                "page": 1,
                "page_size": page_size,
                "total_pages": 0,
                "total_count": 0,
                "is_read": is_read,
                "search": search,
                "unread_count": 0,
                "error": f"Could not list messages: {str(e)}"
            }
        )

@router.get("/view/{message_id}", response_class=HTMLResponse)
async def view_message(
    request: Request,
    message_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    View a single message
    """
    try:
        # Get the message
        message = await Message.get_by_id(message_id)

        if not message:
            # If message not found, redirect to list with error message
            return RedirectResponse(
                url=f"/admin/message/?error=Message with ID {message_id} not found",
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
            "message/view.html",
            {
                "request": request,
                "user": current_user,
                "message": message,
                "user_info": user_info
            }
        )
    except Exception as e:
        logger.error(f"Error viewing message: {str(e)}")
        # Redirect to list with error message
        return RedirectResponse(
            url=f"/admin/message/?error=Error viewing message: {str(e)}",
            status_code=303
        )
