from fastapi import APIRouter, Request, Depends, HTTPException, status, Body
from fastapi.responses import JSONResponse
from typing import Optional, List
from app.models.message import Message
from app.models.user import User
from app.auth.jwt import get_current_active_admin
from app.admin.message import router
from app.database import get_db
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
from datetime import datetime, timezone
from pydantic import BaseModel

# Configure logging
logger = logging.getLogger(__name__)

@router.post("/api/message/{message_id}/mark-read")
async def mark_message_as_read(
    message_id: str,
    is_read: bool = Body(...),
    current_user: User = Depends(get_current_active_admin)
):
    """
    Mark a message as read or unread
    """
    try:
        # Get the message
        message = await Message.get_by_id(message_id)

        if not message:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"success": False, "message": "Message not found"}
            )

        # Update the read status
        message.is_read = is_read
        await message.save()

        return JSONResponse(
            content={
                "success": True,
                "message": f"Message marked as {'read' if is_read else 'unread'}"
            }
        )
    except Exception as e:
        logger.error(f"Error updating message read status: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "message": f"Could not update message status: {str(e)}"}
        )

@router.delete("/api/message/{message_id}")
async def delete_message(
    message_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Delete a message
    """
    try:
        # Get the message
        message = await Message.get_by_id(message_id)

        if not message:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"success": False, "message": "Message not found"}
            )

        # Delete the message
        await message.delete()

        return JSONResponse(
            content={"success": True, "message": "Message deleted successfully"}
        )
    except Exception as e:
        logger.error(f"Error deleting message: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "message": f"Could not delete message: {str(e)}"}
        )
