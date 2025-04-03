from fastapi import APIRouter, Request, Depends, HTTPException, status, Form, UploadFile, File, Query, Body
from fastapi.responses import RedirectResponse, JSONResponse
from typing import Optional, List
from pydantic import BaseModel
from app.models.user import User
from app.auth.jwt import get_current_active_admin
from app.models.banner import Banner, BannerPosition
from app.utils.image import validate_and_optimize_banner_image, delete_images
from uuid import uuid4
import traceback
from datetime import datetime
import re

# Get router and templates from the package
from app.admin.banner import router, templates

@router.get("/")
async def list_banners(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """
    List all banners
    """
    try:
        banners = await Banner.find().sort([("created_at", -1)]).to_list()
        return templates.TemplateResponse(
            "banner/index.html",
            {
                "request": request,
                "banners": banners,
                "user": current_user
            }
        )
    except Exception as e:
        print(f"Error listing banners: {str(e)}")
        print(traceback.format_exc())
        return templates.TemplateResponse(
            "banner/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not list banners: {str(e)}"
            },
            status_code=500
        )

@router.get("/create")
async def create_banner_form(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Display banner creation form
    """
    return templates.TemplateResponse(
        "banner/create.html",
        {
            "request": request,
            "user": current_user,
            "error": None,
            "form_data": None
        }
    )

@router.post("/")
async def create_banner(
    request: Request,
    title: str = Form(...),
    subtitle: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    image: UploadFile = File(...),
    link: Optional[str] = Form(None),
    position: str = Form("home_top"),
    is_active: bool = Form(True),
    current_user: User = Depends(get_current_active_admin)
):
    """
    Create a new banner
    """
    try:
        # Validate and optimize image
        image_url = await validate_and_optimize_banner_image(image)
        
        # Create banner
        banner_data = {
            "id": str(uuid4()),
            "title": title,
            "subtitle": subtitle,
            "description": description,
            "image_url": image_url,
            "link": link,
            "position": position,
            "is_active": is_active
        }
        
        banner = Banner(**banner_data)
        await banner.save()
        
        # Redirect to banner list
        return RedirectResponse(
            url="/admin/banner",
            status_code=303
        )
    except Exception as e:
        print(f"Error creating banner: {str(e)}")
        print(traceback.format_exc())
        
        return templates.TemplateResponse(
            "banner/create.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not create banner: {str(e)}",
                "form_data": {
                    "title": title,
                    "subtitle": subtitle,
                    "description": description,
                    "link": link,
                    "position": position,
                    "is_active": is_active
                }
            },
            status_code=500
        )

@router.get("/{banner_id}/edit")
async def edit_banner_form(
    request: Request,
    banner_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Display banner edit form
    """
    try:
        # First try to find by exact ID match
        banner = await Banner.find_one({"id": banner_id})
        
        if banner is None:
            # Try to find by _id if id not found
            banner = await Banner.find_one({"_id": banner_id})
            
        if not banner:
            return templates.TemplateResponse(
                "banner/404.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "Banner not found"
                },
                status_code=404
            )
        
        return templates.TemplateResponse(
            "banner/edit.html",
            {
                "request": request,
                "banner": banner,
                "user": current_user,
                "error": None
            }
        )
    except Exception as e:
        print(f"Error loading banner: {str(e)}")
        print(traceback.format_exc())
        return templates.TemplateResponse(
            "banner/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not load banner: {str(e)}"
            },
            status_code=500
        )

@router.post("/{banner_id}")
async def edit_banner(
    request: Request,
    banner_id: str,
    title: str = Form(...),
    subtitle: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    link: Optional[str] = Form(None),
    position: str = Form("home_top"),
    is_active: bool = Form(True),
    current_user: User = Depends(get_current_active_admin)
):
    """
    Update an existing banner
    """
    try:
        # First try to find by exact ID match
        banner = await Banner.find_one({"id": banner_id})
        
        if banner is None:
            # Try to find by _id if id not found
            banner = await Banner.find_one({"_id": banner_id})
            
        if not banner:
            return templates.TemplateResponse(
                "banner/404.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "Banner not found"
                },
                status_code=404
            )
        
        # Handle image upload if new image is provided
        if image and image.filename:
            # Store the old image URL to delete later if upload succeeds
            old_image_url = banner.image_url
            
            # Upload new image
            image_url = await validate_and_optimize_banner_image(image)
            
            if image_url:
                # Update the banner with new image URL
                banner.image_url = image_url
                
                # Delete old image once the new one is successfully uploaded
                if old_image_url:
                    delete_result = delete_images([old_image_url])
                    print(f"Replaced banner image: deleted {delete_result['success']} old image, failed to delete {delete_result['failed']}")
        
        # Update banner fields
        banner.title = title
        banner.subtitle = subtitle
        banner.description = description
        banner.link = link
        banner.position = position
        banner.is_active = is_active
        
        # Save the updated banner
        await banner.save()
        
        # Redirect to banner list
        return RedirectResponse(
            url="/admin/banner",
            status_code=303
        )
    except Exception as e:
        print(f"Error updating banner: {str(e)}")
        print(traceback.format_exc())
        
        return templates.TemplateResponse(
            "banner/edit.html",
            {
                "request": request,
                "banner": banner,
                "user": current_user,
                "error": f"Could not update banner: {str(e)}"
            },
            status_code=500
        )

@router.get("/{banner_id}/delete")
async def delete_banner_form(
    request: Request,
    banner_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Display banner deletion confirmation form
    """
    try:
        # First try to find by exact ID match
        banner = await Banner.find_one({"id": banner_id})
        
        if banner is None:
            # Try to find by _id if id not found
            banner = await Banner.find_one({"_id": banner_id})
            
        if not banner:
            return templates.TemplateResponse(
                "banner/404.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "Banner not found"
                },
                status_code=404
            )
        
        return templates.TemplateResponse(
            "banner/delete.html",
            {
                "request": request,
                "banner": banner,
                "user": current_user,
                "error": None
            }
        )
    except Exception as e:
        print(f"Error loading banner: {str(e)}")
        print(traceback.format_exc())
        return templates.TemplateResponse(
            "banner/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not load banner: {str(e)}"
            },
            status_code=500
        )

@router.post("/{banner_id}/delete")
async def delete_banner(
    request: Request,
    banner_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Delete a banner
    """
    try:
        # First try to find by exact ID match
        banner = await Banner.find_one({"id": banner_id})
        
        if banner is None:
            # Try to find by _id if id not found
            banner = await Banner.find_one({"_id": banner_id})
            
        if not banner:
            return templates.TemplateResponse(
                "banner/404.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "Banner not found"
                },
                status_code=404
            )
        
        # Delete image from Cloudinary if it exists
        if banner.image_url:
            result = delete_images([banner.image_url])
            print(f"Deleted banner image: success={result['success']}, failed={result['failed']}")
        
        # Delete the banner
        await banner.delete()
        
        # Redirect to banner list
        return RedirectResponse(
            url="/admin/banner",
            status_code=303
        )
    except Exception as e:
        print(f"Error deleting banner: {str(e)}")
        print(traceback.format_exc())
        
        return templates.TemplateResponse(
            "banner/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not delete banner: {str(e)}"
            },
            status_code=500
        )

@router.get("/api/banners")
async def filter_banners(
    search: Optional[str] = None,
    position: Optional[str] = None,
    status: Optional[str] = None,
    date: Optional[str] = None,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Filter banners based on criteria
    """
    try:
        # Start with base query
        query = {}
        
        # Add search filter if provided
        if search:
            query["title"] = {"$regex": search, "$options": "i"}
        
        # Add position filter if provided
        if position:
            # Convert position to lowercase for case-insensitive matching
            query["position"] = position.lower()
        
        # Add status filter if provided
        if status:
            query["is_active"] = status == "active"
        
        # Add date filter if provided
        if date:
            try:
                date_obj = datetime.strptime(date, "%Y-%m-%d")
                query["created_at"] = {
                    "$gte": date_obj,
                    "$lt": date_obj.replace(hour=23, minute=59, second=59)
                }
            except ValueError:
                print(f"Invalid date format: {date}")
        
        print(f"Query: {query}")  # Debug log
        
        # Execute query
        banners = await Banner.find(query).sort([("created_at", -1)]).to_list()
        
        print(f"Found {len(banners)} banners")  # Debug log
        
        # Convert banners to list of dictionaries
        banner_list = []
        for banner in banners:
            banner_dict = {
                "id": str(banner.id),
                "title": banner.title,
                "subtitle": banner.subtitle,
                "image_url": banner.image_url,
                "position": banner.position,
                "is_active": banner.is_active,
                "created_at": banner.created_at.strftime("%Y-%m-%d %H:%M")
            }
            banner_list.append(banner_dict)
        
        return JSONResponse(content={"banners": banner_list})
        
    except Exception as e:
        print(f"Error filtering banners: {str(e)}")
        print(traceback.format_exc())
        return JSONResponse(
            content={"error": f"Could not filter banners: {str(e)}"},
            status_code=500
        )

@router.post("/api/banners/migrate-home-bottom")
async def migrate_home_bottom_banners(
    current_user: User = Depends(get_current_active_admin)
):
    """
    Migrate all home_bottom banners to home_top
    """
    try:
        # Find all banners with home_bottom position
        banners = await Banner.find({"position": "home_bottom"}).to_list()
        
        # Update each banner to home_top
        for banner in banners:
            banner.position = BannerPosition.HOME_TOP
            await banner.save()
        
        return JSONResponse({
            "message": f"Successfully migrated {len(banners)} banners from home_bottom to home_top",
            "count": len(banners)
        })
    except Exception as e:
        print(f"Error migrating banners: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e)) 