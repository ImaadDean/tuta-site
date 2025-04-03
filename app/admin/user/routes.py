from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import RedirectResponse
from typing import Optional
from app.models.user import User, UserRole
from app.auth.jwt import get_current_active_admin
from app.auth.jwt import get_password_hash
from app.admin.user import router, templates
import logging

# Configure logging
logger = logging.getLogger(__name__)

@router.get("/")
async def list_users(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """
    List all users
    """
    try:
        users = await User.find().sort([("created_at", -1)]).to_list()
        logger.info(f"Found {len(users)} users")
        return templates.TemplateResponse(
            "users/list.html",
            {
                "request": request,
                "users": users,
                "user": current_user
            }
        )
    except Exception as e:
        logger.error(f"Error listing users: {str(e)}")
        return templates.TemplateResponse(
            "users/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not list users: {str(e)}"
            },
            status_code=500
        )

@router.get("/new")
async def create_user_form(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Display user creation form
    """
    return templates.TemplateResponse(
        "users/create.html",
        {
            "request": request,
            "user": current_user,
            "error": None
        }
    )

@router.post("/")
async def create_user(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("client"),
    is_active: bool = Form(True),
    current_user: User = Depends(get_current_active_admin)
):
    """
    Create a new user
    """
    try:
        # Check if username or email already exists
        existing_user = await User.find_one({
            "$or": [
                {"username": username},
                {"email": email}
            ]
        })
        
        if existing_user:
            return templates.TemplateResponse(
                "users/create.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "Username or email already exists"
                },
                status_code=400
            )
        
        # Create new user
        hashed_password = get_password_hash(password)
        user_data = {
            "username": username,
            "email": email,
            "hashed_password": hashed_password,
            "role": UserRole(role),
            "is_active": is_active
        }
        
        user = User(**user_data)
        await user.save()
        logger.info(f"Created new user: {username}")
        
        # Redirect to user list
        return RedirectResponse(
            url="/admin/users",
            status_code=303
        )
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        return templates.TemplateResponse(
            "users/create.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not create user: {str(e)}"
            },
            status_code=500
        )

@router.get("/{user_id}")
async def view_user(
    request: Request,
    user_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    View user details
    """
    try:
        logger.info(f"Attempting to find user with ID: {user_id}")
        user = await User.find_one({"_id": user_id})
        if not user:
            logger.warning(f"User not found with ID: {user_id}")
            return templates.TemplateResponse(
                "users/404.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "User not found"
                },
                status_code=404
            )
        
        logger.info(f"Found user: {user.username}")
        return templates.TemplateResponse(
            "users/detail.html",
            {
                "request": request,
                "view_user": user,
                "user": current_user
            }
        )
    except Exception as e:
        logger.error(f"Error viewing user: {str(e)}")
        return templates.TemplateResponse(
            "users/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not view user: {str(e)}"
            },
            status_code=500
        )

@router.get("/{user_id}/edit")
async def edit_user_form(
    request: Request,
    user_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Display user edit form
    """
    try:
        logger.info(f"Attempting to find user with ID: {user_id}")
        user = await User.find_one({"_id": user_id})
        if not user:
            logger.warning(f"User not found with ID: {user_id}")
            return templates.TemplateResponse(
                "users/404.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "User not found"
                },
                status_code=404
            )
        
        logger.info(f"Found user for edit: {user.username}")
        return templates.TemplateResponse(
            "users/edit.html",
            {
                "request": request,
                "edit_user": user,
                "user": current_user,
                "error": None
            }
        )
    except Exception as e:
        logger.error(f"Error loading user for edit: {str(e)}")
        return templates.TemplateResponse(
            "users/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not load user: {str(e)}"
            },
            status_code=500
        )

@router.post("/{user_id}")
async def edit_user(
    request: Request,
    user_id: str,
    username: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    is_active: bool = Form(True),
    current_user: User = Depends(get_current_active_admin)
):
    """
    Update an existing user
    """
    try:
        logger.info(f"Attempting to find user with ID: {user_id}")
        user = await User.find_one({"_id": user_id})
        if not user:
            logger.warning(f"User not found with ID: {user_id}")
            return templates.TemplateResponse(
                "users/404.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "User not found"
                },
                status_code=404
            )
        
        # Check if username or email is already taken by another user
        existing_user = await User.find_one({
            "$and": [
                {"_id": {"$ne": user_id}},
                {"$or": [
                    {"username": username},
                    {"email": email}
                ]}
            ]
        })
        
        if existing_user:
            return templates.TemplateResponse(
                "users/edit.html",
                {
                    "request": request,
                    "edit_user": user,
                    "user": current_user,
                    "error": "Username or email already exists"
                },
                status_code=400
            )
        
        # Update user fields
        user.username = username
        user.email = email
        user.role = UserRole(role)
        user.is_active = is_active
        
        # Save the updated user
        await user.save()
        logger.info(f"Updated user: {username}")
        
        # Redirect to user list
        return RedirectResponse(
            url="/admin/users",
            status_code=303
        )
    except Exception as e:
        logger.error(f"Error updating user: {str(e)}")
        return templates.TemplateResponse(
            "users/edit.html",
            {
                "request": request,
                "edit_user": user,
                "user": current_user,
                "error": f"Could not update user: {str(e)}"
            },
            status_code=500
        )

@router.get("/{user_id}/delete")
async def delete_user_form(
    request: Request,
    user_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Display user deletion confirmation form
    """
    try:
        logger.info(f"Attempting to find user with ID: {user_id}")
        user = await User.find_one({"_id": user_id})
        if not user:
            logger.warning(f"User not found with ID: {user_id}")
            return templates.TemplateResponse(
                "users/404.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "User not found"
                },
                status_code=404
            )
        
        logger.info(f"Found user for deletion: {user.username}")
        return templates.TemplateResponse(
            "users/delete.html",
            {
                "request": request,
                "delete_user": user,
                "user": current_user,
                "error": None
            }
        )
    except Exception as e:
        logger.error(f"Error loading user for deletion: {str(e)}")
        return templates.TemplateResponse(
            "users/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not load user: {str(e)}"
            },
            status_code=500
        )

@router.post("/{user_id}/delete")
async def delete_user(
    request: Request,
    user_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Delete a user
    """
    try:
        logger.info(f"Attempting to find user with ID: {user_id}")
        user = await User.find_one({"_id": user_id})
        if not user:
            logger.warning(f"User not found with ID: {user_id}")
            return templates.TemplateResponse(
                "users/404.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "User not found"
                },
                status_code=404
            )
        
        # Prevent self-deletion
        if user.id == current_user.id:
            return templates.TemplateResponse(
                "users/error.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": "You cannot delete your own account"
                },
                status_code=400
            )
        
        # Delete the user
        await user.delete()
        logger.info(f"Deleted user: {user.username}")
        
        # Redirect to user list
        return RedirectResponse(
            url="/admin/users",
            status_code=303
        )
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        return templates.TemplateResponse(
            "users/error.html",
            {
                "request": request,
                "user": current_user,
                "error": f"Could not delete user: {str(e)}"
            },
            status_code=500
        ) 