from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, List
from app.models.brand import Brand
from app.models.banner import Banner, BannerPosition
from app.utils.image import validate_and_optimize_brand_image, delete_image
from app.auth.jwt import get_current_active_admin
from app.admin.brand import router, templates
from app.utils.logger import log_error

@router.get("/", response_class=HTMLResponse)
async def list_brands(request: Request, current_user: dict = Depends(get_current_active_admin)):
    """List all brands"""
    try:
        brands = await Brand.find_all().to_list()
        # Get banners for each brand
        for brand in brands:
            if brand.banner_id:
                brand.banner = await Banner.find_one({"_id": brand.banner_id})
        return templates.TemplateResponse(
            "brand/index.html",
            {"request": request, "brands": brands, "user": current_user}
        )
    except Exception as e:
        log_error(f"Error listing brands: {str(e)}")
        request.session["message"] = "Error loading brands"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/brand", status_code=500)

@router.get("/create", response_class=HTMLResponse)
async def create_brand_form(request: Request, current_user: dict = Depends(get_current_active_admin)):
    """Show create brand form"""
    try:
        # Get active banners for brand pages
        banners = await Banner.find({"position": BannerPosition.BRAND_PAGE, "is_active": True}).to_list()
        return templates.TemplateResponse(
            "brand/create.html",
            {"request": request, "banners": banners, "user": current_user}
        )
    except Exception as e:
        log_error(f"Error loading create brand form: {str(e)}")
        request.session["message"] = "Error loading create form"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/brand", status_code=500)

@router.post("/")
async def create_brand(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    icon: UploadFile = File(...),
    banner_id: Optional[str] = Form(None),
    is_active: bool = Form(True),
    is_featured: bool = Form(False),
    order: int = Form(0),
    current_user: dict = Depends(get_current_active_admin)
):
    """Create a new brand"""
    try:
        # Save the icon
        icon_url = await validate_and_optimize_brand_image(icon)
        if not icon_url:
            raise HTTPException(status_code=400, detail="Failed to upload icon")

        # Create brand
        brand = Brand(
            name=name,
            description=description,
            icon_url=icon_url,
            banner_id=banner_id,
            is_active=is_active,
            is_featured=is_featured,
            order=order
        )
        await brand.save()

        request.session["message"] = "Brand created successfully"
        request.session["message_type"] = "success"
        return RedirectResponse(url="/admin/brand", status_code=303)
    except Exception as e:
        log_error(f"Error creating brand: {str(e)}")
        request.session["message"] = "Error creating brand"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/brand/create", status_code=500)

@router.get("/{brand_id}/edit", response_class=HTMLResponse)
async def edit_brand_form(
    request: Request,
    brand_id: str,
    current_user: dict = Depends(get_current_active_admin)
):
    """Show edit brand form"""
    try:
        brand = await Brand.find_one({"_id": brand_id})
        if not brand:
            request.session["message"] = "Brand not found"
            request.session["message_type"] = "error"
            return RedirectResponse(url="/admin/brand/", status_code=303)
        
        # Get active banners for brand pages
        banners = await Banner.find({"position": BannerPosition.BRAND_PAGE, "is_active": True}).to_list()
        return templates.TemplateResponse(
            "brand/edit.html",
            {
                "request": request,
                "brand": brand,
                "banners": banners,
                "user": current_user
            }
        )
    except Exception as e:
        log_error(f"Error loading edit brand form: {str(e)}")
        request.session["message"] = "Error loading edit form"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/brand/", status_code=500)

@router.post("/{brand_id}/edit")
async def update_brand(
    request: Request,
    brand_id: str,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    icon: Optional[UploadFile] = File(None),
    banner_id: Optional[str] = Form(None),
    is_active: bool = Form(True),
    is_featured: bool = Form(False),
    order: int = Form(0),
    current_user: dict = Depends(get_current_active_admin)
):
    """Update a brand"""
    try:
        brand = await Brand.find_one({"_id": brand_id})
        if not brand:
            raise HTTPException(status_code=404, detail="Brand not found")

        # Update basic fields
        brand.name = name
        brand.description = description
        brand.banner_id = banner_id
        brand.is_active = is_active
        brand.is_featured = is_featured
        brand.order = order

        # Handle icon upload if new icon is provided
        if icon:
            # Delete old icon if exists
            if brand.icon_url:
                delete_image(brand.icon_url)
            
            # Save new icon
            icon_url = await validate_and_optimize_brand_image(icon)
            if not icon_url:
                raise HTTPException(status_code=400, detail="Failed to upload icon")
            brand.icon_url = icon_url

        await brand.save()

        request.session["message"] = "Brand updated successfully"
        request.session["message_type"] = "success"
        return RedirectResponse(url="/admin/brand", status_code=303)
    except Exception as e:
        log_error(f"Error updating brand: {str(e)}")
        request.session["message"] = "Error updating brand"
        request.session["message_type"] = "error"
        return RedirectResponse(url=f"/admin/brand/{brand_id}/edit", status_code=500)

@router.get("/{brand_id}/delete", response_class=HTMLResponse)
async def delete_brand_form(
    request: Request,
    brand_id: str,
    current_user: dict = Depends(get_current_active_admin)
):
    """Show delete brand confirmation form"""
    try:
        brand = await Brand.find_one({"_id": brand_id})
        if not brand:
            request.session["message"] = "Brand not found"
            request.session["message_type"] = "error"
            return RedirectResponse(url="/admin/brand/", status_code=303)
        
        return templates.TemplateResponse(
            "brand/delete.html",
            {"request": request, "brand": brand, "user": current_user}
        )
    except Exception as e:
        log_error(f"Error loading delete brand form: {str(e)}")
        request.session["message"] = "Error loading delete form"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/brand/", status_code=500)

@router.post("/{brand_id}/delete")
async def delete_brand(
    request: Request,
    brand_id: str,
    current_user: dict = Depends(get_current_active_admin)
):
    """Delete a brand"""
    try:
        brand = await Brand.find_one({"_id": brand_id})
        if not brand:
            raise HTTPException(status_code=404, detail="Brand not found")

        # Delete associated icon if exists
        if brand.icon_url:
            delete_image(brand.icon_url)

        # Delete the brand
        await brand.delete()

        request.session["message"] = "Brand deleted successfully"
        request.session["message_type"] = "success"
        return RedirectResponse(url="/admin/brand", status_code=303)
    except Exception as e:
        log_error(f"Error deleting brand: {str(e)}")
        request.session["message"] = "Error deleting brand"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/brand", status_code=500) 