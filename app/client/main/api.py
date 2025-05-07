from fastapi import APIRouter, Request, Depends, HTTPException, status, Body
from fastapi.responses import JSONResponse
from app.models.user import User
from app.models.message import Message, MessageUser
from app.auth.jwt import get_current_user_optional
from typing import Optional
import logging
from datetime import datetime

# Create router
router = APIRouter(prefix="/api", tags=["client_api"])

# Configure logging
logger = logging.getLogger(__name__)

@router.post("/contact")
async def submit_contact_form(
    request: Request,
    subject: str = Body(...),
    message: str = Body(...),
    name: Optional[str] = Body(None),
    email: Optional[str] = Body(None),
    phone: Optional[str] = Body(None),
    user_id: Optional[str] = Body(None),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Submit a contact form message"""
    try:
        # Create user info object
        user_info = None

        # If user is logged in, use their information
        if current_user:
            user_info = MessageUser(
                name=current_user.username,
                email=current_user.email,
                phone=getattr(current_user, 'phone_number', None)
            )
            user_id = str(current_user.id)
        # Otherwise use the provided information
        elif name and email:
            user_info = MessageUser(
                name=name,
                email=email,
                phone=phone
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "message": "Name and email are required when not logged in"
                }
            )

        # Create and save the message
        user_message = Message(
            user_info=user_info,
            subject=subject,
            message=message,
            user_id=user_id
        )

        await user_message.save()

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "success": True,
                "message": "Your message has been sent successfully. We'll get back to you soon!"
            }
        )
    except Exception as e:
        logger.error(f"Error submitting contact form: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": "An error occurred while submitting your message. Please try again later."
            }
        )
