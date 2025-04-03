from fastapi import APIRouter, Request, Depends, HTTPException, status, Form, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from typing import Optional
from app.models.category import Category
from app.models.user import User
from app.models.banner import Banner, BannerPosition
from app.auth.jwt import get_current_active_admin
from app.admin.category import router, templates
from app.utils.image import delete_image, save_icon, validate_and_optimize_banner_image
import logging

from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

@router.get("/")
async def list_categories(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """
    List all categories
    """
    try:
        categories = await Category.find_all().to_list()
        # Get banners for each category
        for category in categories:
            if category.banner_id:
                category.banner = await Banner.find_one({"_id": category.banner_id})
        return templates.TemplateResponse(
            "category/index.html",
            {
                "request": request,
                "categories": categories,
                "user": current_user
            }
        )
    except Exception as e:
        logger.error(f"Error listing categories: {str(e)}")
        return templates.TemplateResponse(
            "category/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not list categories: {str(e)}"
            },
            status_code=500
        )

@router.get("/create")
async def create_category_form(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Display form to create a new category
    """
    try:
        # Get active banners for category pages
        banners = await Banner.find({"position": BannerPosition.CATEGORY_PAGE, "is_active": True}).to_list()
        return templates.TemplateResponse(
            "category/create.html",
            {
                "request": request,
                "banners": banners,
                "user": current_user
            }
        )
    except Exception as e:
        logger.error(f"Error loading create form: {str(e)}")
        return templates.TemplateResponse(
            "category/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not load create form: {str(e)}"
            },
            status_code=500
        )

@router.post("/")
async def create_category(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    icon: UploadFile = File(...),
    banner_id: Optional[str] = Form(None),
    is_active: bool = Form(True),
    current_user: User = Depends(get_current_active_admin)
):
    """
    Create a new category
    """
    try:
        # Check if category name already exists
        existing_category = await Category.find_one({"name": name})
        if existing_category:
            return templates.TemplateResponse(
                "category/create.html",
                {
                    "request": request,
                    "user": current_user,
                    "message": "Category name already exists",
                    "message_type": "error",
                    "form_data": {"name": name, "description": description, "is_active": is_active}
                }
            )

        # Save icon using Cloudinary
        icon_url = await save_icon(icon)

        # Create new category
        category = Category(
            name=name,
            description=description,
            icon_url=icon_url,
            banner_id=banner_id,
            is_active=is_active,
            created_at=datetime.now()
        )
        await category.save()

        return RedirectResponse(
            url="/admin/category",
            status_code=303
        )
    except Exception as e:
        logger.error(f"Error creating category: {str(e)}")
        return templates.TemplateResponse(
            "category/create.html",
            {
                "request": request,
                "user": current_user,
                "message": f"Could not create category: {str(e)}",
                "message_type": "error",
                "form_data": {"name": name, "description": description, "is_active": is_active}
            }
        )

@router.get("/{category_id}/edit")
async def edit_category_form(
    request: Request,
    category_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Display form to edit a category
    """
    try:
        category = await Category.find_one({"_id": category_id})
        if not category:
            return templates.TemplateResponse(
                "category/404.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "Category not found"
                },
                status_code=404
            )
        
        # Get active banners for category pages
        banners = await Banner.find({"position": BannerPosition.CATEGORY_PAGE, "is_active": True}).to_list()
        
        return templates.TemplateResponse(
            "category/edit.html",
            {
                "request": request,
                "category": category,
                "banners": banners,
                "user": current_user
            }
        )
    except Exception as e:
        logger.error(f"Error loading category for edit: {str(e)}")
        return templates.TemplateResponse(
            "category/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not load category: {str(e)}"
            },
            status_code=500
        )

@router.post("/{category_id}")
async def update_category(
    request: Request,
    category_id: str,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    icon: Optional[UploadFile] = File(None),
    banner_id: Optional[str] = Form(None),
    is_active: bool = Form(True),
    current_user: User = Depends(get_current_active_admin)
):
    """
    Update a category
    """
    try:
        category = await Category.find_one({"_id": category_id})
        if not category:
            return templates.TemplateResponse(
                "category/404.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "Category not found"
                },
                status_code=404
            )

        # Check if new name conflicts with existing category
        existing_category = await Category.find_one({
            "name": name,
            "_id": {"$ne": category_id}
        })
        if existing_category:
            return templates.TemplateResponse(
                "category/edit.html",
                {
                    "request": request,
                    "category": category,
                    "user": current_user,
                    "message": "Category name already exists",
                    "message_type": "error"
                }
            )

        # Update category fields
        category.name = name
        category.description = description
        category.is_active = is_active
        category.banner_id = banner_id

        # Handle icon upload if provided
        if icon:
            # Delete old icon from Cloudinary if it exists
            if category.icon_url:
                delete_image(category.icon_url)
            
            # Upload new icon
            icon_url = await save_icon(icon)
            category.icon_url = icon_url

        await category.save()

        return RedirectResponse(
            url="/admin/category",
            status_code=303
        )
    except Exception as e:
        logger.error(f"Error updating category: {str(e)}")
        return templates.TemplateResponse(
            "category/edit.html",
            {
                "request": request,
                "category": category,
                "user": current_user,
                "message": f"Could not update category: {str(e)}",
                "message_type": "error"
            }
        )

@router.get("/{category_id}/delete")
async def delete_category_form(
    request: Request,
    category_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Display confirmation form for category deletion
    """
    try:
        category = await Category.find_one({"_id": category_id})
        if not category:
            return templates.TemplateResponse(
                "category/404.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "Category not found"
                },
                status_code=404
            )
        
        return templates.TemplateResponse(
            "category/delete.html",
            {
                "request": request,
                "category": category,
                "user": current_user
            }
        )
    except Exception as e:
        logger.error(f"Error loading category for deletion: {str(e)}")
        return templates.TemplateResponse(
            "category/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not load category: {str(e)}"
            },
            status_code=500
        )

@router.post("/{category_id}/delete")
async def delete_category(
    request: Request,
    category_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Delete a category
    """
    try:
        category = await Category.find_one({"_id": category_id})
        if not category:
            return templates.TemplateResponse(
                "category/404.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "Category not found"
                },
                status_code=404
            )

        # Delete the category
        await category.delete()

        return RedirectResponse(
            url="/admin/category",
            status_code=303
        )
    except Exception as e:
        logger.error(f"Error deleting category: {str(e)}")
        return templates.TemplateResponse(
            "category/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not delete category: {str(e)}"
            },
            status_code=500
        ) 