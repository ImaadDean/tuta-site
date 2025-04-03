from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, HTMLResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.database import get_db
from app.models.user import User, UserRole
from app.auth.jwt import (
    verify_password,
    get_password_hash,
    get_current_active_admin
)
from app.admin.account import router, templates
from typing import Optional
from app.utils.image import save_image  # Import the save_image function
from datetime import datetime

@router.get("/", response_class=HTMLResponse)
async def account_page(
    request: Request,
    current_user: User = Depends(get_current_active_admin),
    success: Optional[str] = None,
    error: Optional[str] = None
):
    """
    Display the admin account management page
    """
    return templates.TemplateResponse(
        "account/index.html",
        {
            "request": request,
            "user": current_user,
            "success": success,
            "error": error
        }
    )

@router.post("/upload-profile-picture", response_class=HTMLResponse)
async def upload_profile_picture(
    request: Request,
    profile_picture: UploadFile = File(...),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    Upload a new profile picture for the admin
    """
    try:
        # Check if the file is an image
        content_type = profile_picture.content_type
        if not content_type.startswith("image/"):
            return templates.TemplateResponse(
                "account/index.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "Uploaded file is not an image"
                },
                status_code=400
            )
        
        # Debug logging
        print(f"Processing image upload: filename={profile_picture.filename}, content_type={content_type}")
        
        # Upload the image to Cloudinary with optimization
        profile_pic_url = save_image(
            profile_picture, 
            folder="profile_pictures",
            optimize=True,
            max_size=800,  # Reduce size for profile pictures
            quality=85
        )
        
        if not profile_pic_url:
            return templates.TemplateResponse(
                "account/index.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "Failed to upload image"
                },
                status_code=500
            )
        
        # Debug logging
        print(f"Image uploaded successfully to: {profile_pic_url}")
        
        # Update the user's profile picture URL (using Beanie's document methods)
        current_user.profile_picture = profile_pic_url
        await current_user.save()
        
        return RedirectResponse(
            url="/admin/account?success=Profile picture updated successfully",
            status_code=status.HTTP_303_SEE_OTHER
        )
    
    except Exception as e:
        print(f"Profile picture upload error: {str(e)}")
        # More detailed error response
        error_message = f"An error occurred: {str(e)}"
        return templates.TemplateResponse(
            "account/index.html",
            {
                "request": request,
                "user": current_user,
                "error": error_message
            },
            status_code=500
        )

@router.post("/update-profile", response_class=HTMLResponse)
async def update_profile(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    Update the admin's profile information (username and email)
    """
    try:
        # Check if username is already taken by another user
        if username != current_user.username:
            existing_user = await User.find_one({"username": username})
            if existing_user:
                return templates.TemplateResponse(
                    "account/index.html",
                    {
                        "request": request,
                        "user": current_user,
                        "error": "Username already taken"
                    },
                    status_code=400
                )
        
        # Check if email is already taken by another user
        if email != current_user.email:
            existing_user = await User.find_one({"email": email})
            if existing_user:
                return templates.TemplateResponse(
                    "account/index.html",
                    {
                        "request": request,
                        "user": current_user,
                        "error": "Email already registered"
                    },
                    status_code=400
                )
        
        # Update user profile with Beanie
        current_user.username = username
        current_user.email = email
        current_user.updated_at = datetime.utcnow()
        await current_user.save()
        
        return RedirectResponse(
            url="/admin/account?success=Profile updated successfully",
            status_code=status.HTTP_303_SEE_OTHER
        )
    
    except Exception as e:
        print(f"Profile update error: {e}")
        return templates.TemplateResponse(
            "account/index.html",
            {
                "request": request,
                "user": current_user,
                "error": "An error occurred while updating your profile"
            },
            status_code=500
        )

@router.post("/change-password", response_class=HTMLResponse)
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    Change the admin's password
    """
    try:
        # Verify current password
        if not verify_password(current_password, current_user.hashed_password):
            return templates.TemplateResponse(
                "account/index.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "Current password is incorrect"
                },
                status_code=400
            )
        
        # Check if new passwords match
        if new_password != confirm_password:
            return templates.TemplateResponse(
                "account/index.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "New passwords do not match"
                },
                status_code=400
            )
        
        # Update password with Beanie
        current_user.hashed_password = get_password_hash(new_password)
        current_user.updated_at = datetime.utcnow()
        await current_user.save()
        
        return RedirectResponse(
            url="/admin/account?success=Password changed successfully",
            status_code=status.HTTP_303_SEE_OTHER
        )
    
    except Exception as e:
        print(f"Password change error: {e}")
        return templates.TemplateResponse(
            "account/index.html",
            {
                "request": request,
                "user": current_user,
                "error": "An error occurred while changing your password"
            },
            status_code=500
        )
    
# Add this new route to your existing routes.py file

@router.get("/deactivate", response_class=HTMLResponse)
async def deactivate_account(
    request: Request,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    Deactivate the admin's account
    """
    try:
        # Set the user's is_active status to False with Beanie
        current_user.is_active = False
        current_user.updated_at = datetime.utcnow()
        await current_user.save()
        
        # Log the user out
        response = RedirectResponse(
            url="/auth/logout",
            status_code=status.HTTP_303_SEE_OTHER
        )
        
        return response
    
    except Exception as e:
        print(f"Account deactivation error: {e}")
        return templates.TemplateResponse(
            "account/index.html",
            {
                "request": request,
                "user": current_user,
                "error": "An error occurred while deactivating your account"
            },
            status_code=500
        ) 