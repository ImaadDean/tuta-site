from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
from app.models.user import User, UserRole, UserStatus
from app.admin.user import router
from app.auth.jwt import get_current_active_admin
import logging
from math import ceil
from datetime import datetime, timezone

# Configure logging
logger = logging.getLogger(__name__)

@router.get("/api/get-users")
async def get_users(
    search: Optional[str] = None,
    role: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(8, ge=1, le=100),
    skip: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_admin)
):
    """
    Get users with pagination, search, and filtering.

    Parameters:
    - search: Search by username or email
    - role: Filter by role (admin, client)
    - status: Filter by status (active, inactive)
    - limit: Number of users to return (default: 8)
    - skip: Number of users to skip (default: 0)
    """
    try:
        # Build query filters
        query_filter = {}

        # Add search filter
        if search:
            search = search.strip()
            query_filter["$or"] = [
                {"username": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}}
            ]

        # Add role filter
        if role:
            if role.lower() == "admin":
                query_filter["role"] = UserRole.ADMIN
            elif role.lower() == "client":
                query_filter["role"] = UserRole.CLIENT

        # Add status filter
        if status:
            if status.lower() == "active":
                query_filter["is_active"] = True
                query_filter["status"] = {"$ne": UserStatus.DELETED.value}
            elif status.lower() == "inactive":
                query_filter["is_active"] = False
                query_filter["status"] = {"$ne": UserStatus.DELETED.value}
            elif status.lower() == "deleted":
                query_filter["status"] = UserStatus.DELETED.value

        # Get total count for pagination
        total = await User.find(query_filter).count()

        # Get users with pagination
        users = await User.find(query_filter).sort([("created_at", -1)]).skip(skip).limit(limit).to_list()

        # Format users for response
        formatted_users = []
        for user in users:
            formatted_users.append({
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role.value,
                "is_active": user.is_active,
                "status": user.status.value if hasattr(user, 'status') else 'active',
                "created_at": user.created_at.isoformat(),
                "phone_number": user.phone_number if user.phone_number else None,
                "profile_picture": user.profile_picture if user.profile_picture else None
            })

        # Calculate pagination info
        current_page = skip // limit + 1
        total_pages = ceil(total / limit)
        has_more = skip + limit < total

        # Calculate items showing range
        start_item = skip + 1 if total > 0 else 0
        end_item = min(skip + limit, total)
        items_showing = f"{start_item}-{end_item} of {total}"

        # Return response
        return {
            "success": True,
            "users": formatted_users,
            "total": total,
            "has_more": has_more,
            "pagination": {
                "current_page": current_page,
                "total_pages": total_pages,
                "items_showing": items_showing
            }
        }
    except Exception as e:
        logger.error(f"Error getting users: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while fetching users: {str(e)}"
        )

@router.get("/api/get-user-stats")
async def get_user_stats(
    current_user: User = Depends(get_current_active_admin)
):
    """
    Get user statistics for the dashboard.
    """
    try:
        # Get total users count
        total_users = await User.find().count()

        # Get active users count
        active_users = await User.find({"is_active": True}).count()

        # Get admin users count
        admin_users = await User.find({"role": UserRole.ADMIN}).count()

        # Get client users count
        client_users = await User.find({"role": UserRole.CLIENT}).count()

        # Get new users in the last 7 days
        from datetime import datetime, timedelta
        seven_days_ago = datetime.now() - timedelta(days=7)
        new_users = await User.find({"created_at": {"$gte": seven_days_ago}}).count()

        # Return response
        return {
            "success": True,
            "stats": {
                "total_users": total_users,
                "active_users": active_users,
                "admin_users": admin_users,
                "client_users": client_users,
                "new_users_last_7_days": new_users
            }
        }
    except Exception as e:
        logger.error(f"Error getting user stats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while fetching user stats: {str(e)}"
        )

@router.delete("/api/{user_id}/delete")
async def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Delete a user by ID.

    Parameters:
    - user_id: The ID of the user to delete

    Returns:
    - success: True if the user was deleted successfully
    - message: A message indicating the result of the operation
    """
    try:
        # Check if the user exists
        user = await User.find_one({"_id": user_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )

        # Prevent self-deletion
        if user.id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot delete your own account"
            )

        # Mark the user as deleted instead of actually deleting
        user.status = UserStatus.DELETED
        user.is_active = False
        user.updated_at = datetime.now(timezone.utc)
        await user.save()

        logger.info(f"User {user.username} (ID: {user_id}) marked as deleted by admin {current_user.username}")

        # Return success response
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "message": f"User {user.username} marked as deleted successfully",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "status": user.status.value,
                    "is_active": user.is_active
                }
            }
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log the error and return a 500 response
        logger.error(f"Error deleting user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while deleting the user: {str(e)}"
        )
