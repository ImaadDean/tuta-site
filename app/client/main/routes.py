from fastapi import Request, Depends, HTTPException
from app.client.main import router, templates
from fastapi.templating import Jinja2Templates
from app.models.product import Product
from app.models.banner import Banner
from app.models.collection import Collection
from app.models.category import Category
from app.database import get_db, initialize_mongodb
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import uuid
from fastapi.responses import RedirectResponse
import logging
from fastapi.responses import HTMLResponse
from typing import Optional, Dict, Any, List
from app.auth.jwt import get_current_user_optional, get_current_active_client
from app.models.user import User
import asyncio

logger = logging.getLogger(__name__)

# Error handling helper
async def safe_db_operation(operation, fallback_value=None, error_message="Database operation failed"):
    """Execute a database operation safely with error handling"""
    try:
        return await operation
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            logger.error(f"Event loop closed during database operation: {str(e)}")
            # Create a new event loop if the current one is closed
            try:
                # Try to re-initialize the database connection
                await initialize_mongodb()
                # Try the operation again with a fresh connection
                try:
                    return await operation
                except Exception as retry_error:
                    logger.error(f"Failed retry after event loop closed: {str(retry_error)}")
                    return fallback_value
            except Exception as conn_error:
                logger.error(f"Failed to re-initialize connection: {str(conn_error)}")
                return fallback_value
        raise
    except asyncio.CancelledError:
        logger.error("Database operation was cancelled (serverless timeout)")
        return fallback_value
    except Exception as e:
        logger.error(f"{error_message}: {str(e)}")
        # For other exceptions, also return the fallback
        return fallback_value

@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_active_client)
):
    try:

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "current_user": current_user
            }
        )
    except Exception as e:
        logger.error(f"Error rendering home page: {str(e)}")
        return templates.TemplateResponse(
                "index.html",
            {
                "request": request,
                "current_user": current_user
            }
            )

@router.get("/about", response_class=HTMLResponse)
async def about_page(
    request: Request,
    current_user: Optional[User] = Depends(get_current_active_client)
):
    """About page with company information"""
    try:
        # Categories and collections will be loaded client-side via API

        # Bestseller products will be loaded client-side via API

        return templates.TemplateResponse(
            "about.html",
            {
                "request": request,
                "current_user": current_user
            }
        )
    except Exception as e:
        logger.error(f"Error rendering about page: {str(e)}")
        return templates.TemplateResponse(
            "about.html",
            {
                "request": request,
                "current_user": current_user,
                "error_message": "Failed to load some content. Please refresh the page."
            }
        )

@router.get("/contact", response_class=HTMLResponse)
async def contact_page(
    request: Request,
    current_user: Optional[User] = Depends(get_current_active_client)
):
    """Contact page with contact form and information"""
    try:
        # Categories, collections, and bestseller products will be loaded client-side via API

        # Get contact information from database
        from app.models.contact_info import ContactInfo
        contact_info = await safe_db_operation(
            ContactInfo.get_active(),
            fallback_value=None,
            error_message="Failed to fetch contact information"
        )

        # Bestseller products will be loaded client-side via API

        return templates.TemplateResponse(
            "contact.html",
            {
                "request": request,
                "current_user": current_user,
                "contact_info": contact_info
            }
        )
    except Exception as e:
        logger.error(f"Error rendering contact page: {str(e)}")
        return templates.TemplateResponse(
            "contact.html",
            {
                "request": request,
                "current_user": current_user,
                "contact_info": None,
                "error_message": "Failed to load some content. Please refresh the page."
            }
        )