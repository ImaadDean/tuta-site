from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
from app.models.collection import Collection
from app.utils.image import validate_and_optimize_collection_image, delete_image
from app.models.banner import Banner
from app.auth.jwt import get_current_active_admin
from app.admin.collection import router, templates
from app.utils.logger import log_error

@router.get("/", response_class=HTMLResponse)
async def list_collections(request: Request, current_user: dict = Depends(get_current_active_admin)):
    """List all collections"""
    try:
        collections = await Collection.find_all().to_list()
        return templates.TemplateResponse(
            "collection/index.html",
            {"request": request, "collections": collections, "user": current_user}
        )
    except Exception as e:
        log_error(f"Error listing collections: {str(e)}")
        request.session["message"] = "Error loading collections"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/collection", status_code=500)

@router.get("/create", response_class=HTMLResponse)
async def create_collection_form(request: Request, current_user: dict = Depends(get_current_active_admin)):
    """Show create collection form"""
    try:
        banners = await Banner.find({"position": "collection_page", "is_active": True}).to_list()
        return templates.TemplateResponse(
            "collection/create.html",
            {"request": request, "banners": banners, "user": current_user}
        )
    except Exception as e:
        log_error(f"Error loading create collection form: {str(e)}")
        request.session["message"] = "Error loading create form"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/collection", status_code=500)

@router.post("/")
async def create_collection(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    image: UploadFile = File(...),
    banner_id: Optional[str] = Form(None),
    is_active: bool = Form(True),
    current_user: dict = Depends(get_current_active_admin)
):
    """Create a new collection"""
    try:
        # Save the image
        image_url = await validate_and_optimize_collection_image(image)
        if not image_url:
            raise HTTPException(status_code=400, detail="Failed to upload image")

        # Create collection
        collection = Collection(
            name=name,
            description=description,
            image_url=image_url,
            banner_id=banner_id,
            is_active=is_active
        )
        await collection.save()

        request.session["message"] = "Collection created successfully"
        request.session["message_type"] = "success"
        return RedirectResponse(url="/admin/collection", status_code=303)
    except Exception as e:
        log_error(f"Error creating collection: {str(e)}")
        request.session["message"] = "Error creating collection"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/collection/create", status_code=500)

@router.get("/{collection_id}/edit", response_class=HTMLResponse)
async def edit_collection_form(
    request: Request,
    collection_id: str,
    current_user: dict = Depends(get_current_active_admin)
):
    """Show edit collection form"""
    try:
        collection = await Collection.find_one({"_id": collection_id})
        if not collection:
            request.session["message"] = "Collection not found"
            request.session["message_type"] = "error"
            return RedirectResponse(url="/admin/collection/", status_code=303)
        
        banners = await Banner.find({"position": "collection_page", "is_active": True}).to_list()
        return templates.TemplateResponse(
            "collection/edit.html",
            {
                "request": request,
                "collection": collection,
                "banners": banners,
                "user": current_user
            }
        )
    except Exception as e:
        log_error(f"Error loading edit collection form: {str(e)}")
        request.session["message"] = "Error loading edit form"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/collection/", status_code=500)

@router.post("/{collection_id}/edit")
async def update_collection(
    request: Request,
    collection_id: str,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    banner_id: Optional[str] = Form(None),
    is_active: bool = Form(True),
    current_user: dict = Depends(get_current_active_admin)
):
    """Update a collection"""
    try:
        collection = await Collection.find_one({"_id": collection_id})
        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")

        # Update basic fields
        collection.name = name
        collection.description = description
        collection.banner_id = banner_id
        collection.is_active = is_active

        # Handle image upload if new image is provided
        if image:
            # Delete old image if exists
            if collection.image_url:
                delete_image(collection.image_url)
            
            # Save new image
            image_url = await validate_and_optimize_collection_image(image)
            if not image_url:
                raise HTTPException(status_code=400, detail="Failed to upload image")
            collection.image_url = image_url

        await collection.save()

        request.session["message"] = "Collection updated successfully"
        request.session["message_type"] = "success"
        return RedirectResponse(url="/admin/collection", status_code=303)
    except Exception as e:
        log_error(f"Error updating collection: {str(e)}")
        request.session["message"] = "Error updating collection"
        request.session["message_type"] = "error"
        return RedirectResponse(url=f"/admin/collection/{collection_id}/edit", status_code=500)

@router.get("/{collection_id}/delete", response_class=HTMLResponse)
async def delete_collection_form(
    request: Request,
    collection_id: str,
    current_user: dict = Depends(get_current_active_admin)
):
    """Show delete collection confirmation form"""
    try:
        collection = await Collection.find_one({"_id": collection_id})
        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")
        
        return templates.TemplateResponse(
            "collection/delete.html",
            {"request": request, "collection": collection, "user": current_user}
        )
    except Exception as e:
        log_error(f"Error loading delete collection form: {str(e)}")
        request.session["message"] = "Error loading delete form"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/collection", status_code=500)

@router.post("/{collection_id}/delete")
async def delete_collection(
    request: Request,
    collection_id: str,
    current_user: dict = Depends(get_current_active_admin)
):
    """Delete a collection"""
    try:
        collection = await Collection.find_one({"_id": collection_id})
        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")

        # Delete associated image if exists
        if collection.image_url:
            delete_image(collection.image_url)

        # Delete the collection
        await collection.delete()

        request.session["message"] = "Collection deleted successfully"
        request.session["message_type"] = "success"
        return RedirectResponse(url="/admin/collection", status_code=303)
    except Exception as e:
        log_error(f"Error deleting collection: {str(e)}")
        request.session["message"] = "Error deleting collection"
        request.session["message_type"] = "error"
        return RedirectResponse(url="/admin/collection", status_code=500) 