from fastapi import APIRouter, Request, Depends, HTTPException, status, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from typing import Optional, List
from app.models.contact_info import ContactInfo
from app.models.user import User
from app.auth.jwt import get_current_active_admin
from app.admin.contact_info import router, templates
from app.database import get_db
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

@router.get("/", response_class=HTMLResponse)
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
            "contact_info/settings.html",
            {
                "request": request,
                "user": current_user,
                "contact_info": contact_info
            }
        )
    except Exception as e:
        logger.error(f"Error loading contact settings: {str(e)}")
        # Return template with error message
        return templates.TemplateResponse(
            "contact_info/settings.html",
            {
                "request": request,
                "user": current_user,
                "contact_info": None,
                "error": f"Error loading contact settings: {str(e)}"
            }
        )
