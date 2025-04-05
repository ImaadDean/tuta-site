from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, List
from app.models.scent import Scent
from app.models.banner import Banner, BannerPosition
from app.utils.image import validate_and_optimize_scent_image, delete_image
from app.auth.jwt import get_current_active_admin
from app.admin.scent import router, templates
from app.utils.logger import log_error

@router.get("/", response_class=HTMLResponse)
async def list_scents(request: Request, current_user: dict = Depends(get_current_active_admin)):
    """List all scents"""
    try:
        scents = await Scent.find_all().to_list()
        # Get banners for each scent
        for scent in scents:
            if scent.banner_id:
                scent.banner = await Banner.find_one({"_id": scent.banner_id})
        return templates.TemplateResponse(
            "scent/index.html",
            {"request": request, "scents": scents, "user": current_user}
        )
    except Exception as e:
        log_error(f"Error listing scents: {str(e)}")
        request.session["message"] = "Error loading scents"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/scent", status_code=500)

@router.get("/create", response_class=HTMLResponse)
async def create_scent_form(request: Request, current_user: dict = Depends(get_current_active_admin)):
    """Show create scent form"""
    try:
        # Get active banners for scent pages
        banners = await Banner.find({"position": BannerPosition.SCENT_PAGE, "is_active": True}).to_list()
        return templates.TemplateResponse(
            "scent/create.html",
            {"request": request, "banners": banners, "user": current_user}
        )
    except Exception as e:
        log_error(f"Error loading create scent form: {str(e)}")
        request.session["message"] = "Error loading create form"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/scent", status_code=500)

@router.post("/")
async def create_scent(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    image: UploadFile = File(...),
    banner_id: Optional[str] = Form(None),
    is_active: bool = Form(True),
    current_user: dict = Depends(get_current_active_admin)
):
    """Create a new scent"""
    try:
        # Save the image
        image_url = await validate_and_optimize_scent_image(image)
        if not image_url:
            raise HTTPException(status_code=400, detail="Failed to upload image")

        # Create scent
        scent = Scent(
            name=name,
            description=description,
            image_url=image_url,
            banner_id=banner_id,
            is_active=is_active
        )
        await scent.save()

        request.session["message"] = "Scent created successfully"
        request.session["message_type"] = "success"
        return RedirectResponse(url="/admin/scent", status_code=303)
    except Exception as e:
        log_error(f"Error creating scent: {str(e)}")
        request.session["message"] = "Error creating scent"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/scent/create", status_code=500)

@router.get("/{scent_id}/edit", response_class=HTMLResponse)
async def edit_scent_form(
    request: Request,
    scent_id: str,
    current_user: dict = Depends(get_current_active_admin)
):
    """Show edit scent form"""
    try:
        scent = await Scent.find_one({"_id": scent_id})
        if not scent:
            request.session["message"] = "Scent not found"
            request.session["message_type"] = "error"
            return RedirectResponse(url="/admin/scent/", status_code=303)
        
        # Get active banners for scent pages
        banners = await Banner.find({"position": BannerPosition.SCENT_PAGE, "is_active": True}).to_list()
        return templates.TemplateResponse(
            "scent/edit.html",
            {
                "request": request,
                "scent": scent,
                "banners": banners,
                "user": current_user
            }
        )
    except Exception as e:
        log_error(f"Error loading edit scent form: {str(e)}")
        request.session["message"] = "Error loading edit form"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/scent/", status_code=500)

@router.post("/{scent_id}/edit")
async def update_scent(
    request: Request,
    scent_id: str,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    banner_id: Optional[str] = Form(None),
    is_active: bool = Form(True),
    current_user: dict = Depends(get_current_active_admin)
):
    """Update a scent"""
    try:
        scent = await Scent.find_one({"_id": scent_id})
        if not scent:
            raise HTTPException(status_code=404, detail="Scent not found")

        # Update basic fields
        scent.name = name
        scent.description = description
        scent.banner_id = banner_id if banner_id else None  # Ensure None is stored if empty string
        scent.is_active = is_active

        # Handle image upload if new image is provided
        if image and image.filename:  # Check if image has a filename
            # Delete old image if exists
            if scent.image_url:
                delete_image(scent.image_url)
            
            # Save new image
            image_url = await validate_and_optimize_scent_image(image)
            if not image_url:
                raise HTTPException(status_code=400, detail="Failed to upload image")
            scent.image_url = image_url

        await scent.save()

        request.session["message"] = "Scent updated successfully"
        request.session["message_type"] = "success"
        return RedirectResponse(url="/admin/scent", status_code=303)
    except Exception as e:
        log_error(f"Error updating scent: {str(e)}")
        request.session["message"] = "Error updating scent"
        request.session["message_type"] = "error"
        return RedirectResponse(url=f"/admin/scent/{scent_id}/edit", status_code=500)

@router.get("/{scent_id}/delete", response_class=HTMLResponse)
async def delete_scent_form(
    request: Request,
    scent_id: str,
    current_user: dict = Depends(get_current_active_admin)
):
    """Show delete scent confirmation form"""
    try:
        scent = await Scent.find_one({"_id": scent_id})
        if not scent:
            request.session["message"] = "Scent not found"
            request.session["message_type"] = "error"
            return RedirectResponse(url="/admin/scent/", status_code=303)
        
        return templates.TemplateResponse(
            "scent/delete.html",
            {"request": request, "scent": scent, "user": current_user}
        )
    except Exception as e:
        log_error(f"Error loading delete scent form: {str(e)}")
        request.session["message"] = "Error loading delete form"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/scent/", status_code=500)

@router.post("/{scent_id}/delete")
async def delete_scent(
    request: Request,
    scent_id: str,
    current_user: dict = Depends(get_current_active_admin)
):
    """Delete a scent"""
    try:
        scent = await Scent.find_one({"_id": scent_id})
        if not scent:
            raise HTTPException(status_code=404, detail="Scent not found")

        # Delete associated image if exists
        if scent.image_url:
            delete_image(scent.image_url)

        # Delete the scent
        await scent.delete()

        request.session["message"] = "Scent deleted successfully"
        request.session["message_type"] = "success"
        return RedirectResponse(url="/admin/scent", status_code=303)
    except Exception as e:
        log_error(f"Error deleting scent: {str(e)}")
        request.session["message"] = "Error deleting scent"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/scent", status_code=500) 