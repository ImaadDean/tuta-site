from fastapi import Request, Depends, HTTPException, status
from app.client.category import router, templates
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional, Dict, Any
from app.models.category import Category
from app.models.product import Product
from app.models.collection import Collection
from app.auth.jwt import get_current_active_client
from app.models.user import User
import logging
from contextlib import contextmanager
from time import time

# Configure logger
logger = logging.getLogger(__name__)

@contextmanager
def log_execution_time(operation: str):
    """Context manager to log execution time of operations"""
    start_time = time()
    try:
        yield
    finally:
        execution_time = time() - start_time
        logger.debug(f"{operation} completed in {execution_time:.2f}s")

def create_template_context(request: Request, current_user: Optional[User] = None, **kwargs) -> Dict[str, Any]:
    """Create a base template context with common variables"""
    context = {
        "request": request,
        "current_user": current_user,
    }
    context.update(kwargs)
    return context

@router.get("/", response_class=HTMLResponse)
async def get_all_categories(
    request: Request,
    current_user: Optional[User] = Depends(get_current_active_client)
):
    """
    Render the categories page showing all available categories
    
    Args:
        request: The FastAPI request object
        current_user: The authenticated user (optional)
        
    Returns:
        HTMLResponse: The rendered categories page
    """
    with log_execution_time("Rendering categories page"):
        try:
            # Categories will be loaded client-side via API
            return templates.TemplateResponse(
                "categories/categories.html",
                create_template_context(
                    request=request,
                    current_user=current_user,
                    page_title="All Categories"
                )
            )
        except Exception as e:
            logger.error(f"Error rendering categories page: {str(e)}", exc_info=True)
            return templates.TemplateResponse(
                "categories/categories.html",
                create_template_context(
                    request=request,
                    current_user=current_user,
                    page_title="All Categories",
                    error_message="Failed to load categories. Please try again later."
                ),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

@router.get("/{category_id}", response_class=HTMLResponse)
async def get_category_detail(
    request: Request,
    category_id: str,
    current_user: Optional[User] = Depends(get_current_active_client)
):
    """
    Render the category detail page showing products in the selected category
    
    Args:
        request: The FastAPI request object
        category_id: The ID of the category to display
        current_user: The authenticated user (optional)
        
    Returns:
        HTMLResponse: The rendered category detail page
        RedirectResponse: Redirect to categories page if category not found
    """
    with log_execution_time(f"Rendering category detail page for {category_id}"):
        try:
            # Get the category
            category = await Category.find_one({"_id": category_id})
            if not category:
                logger.warning(f"Category not found: {category_id}")
                # If category not found, redirect to all categories page
                return RedirectResponse(url="/categories", status_code=status.HTTP_302_FOUND)

            # Products will be loaded client-side via API
            return templates.TemplateResponse(
                "categories/category_detail.html",
                create_template_context(
                    request=request,
                    current_user=current_user,
                    category=category,
                    page_title=category.name
                )
            )
        except Exception as e:
            logger.error(f"Error rendering category detail page for {category_id}: {str(e)}", exc_info=True)
            return templates.TemplateResponse(
                "categories/category_detail.html",
                create_template_context(
                    request=request,
                    current_user=current_user,
                    category_id=category_id,
                    page_title="Category Details",
                    error_message="Failed to load category details. Please try again later."
                ),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )