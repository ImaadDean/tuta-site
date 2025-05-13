from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from app.models.user import User
from app.auth.jwt import get_current_active_admin
from app.admin.dashboard import templates, router
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

@router.get("/", response_class=HTMLResponse)
async def admin_home(
    request: Request,
    current_user: User = Depends(get_current_active_admin)
):
    """Dashboard page with stats cards that fetch data from API"""
    try:
        return templates.TemplateResponse(
            "dashboard/dashboard.html",
            {
                "request": request,
                "user": current_user,
                "current_date": datetime.now()
            }
        )
    except Exception as e:
        logger.error(f"Error loading dashboard: {str(e)}")
        return HTMLResponse(
            content=f"""
            <html>
                <head><title>Admin Dashboard</title></head>
                <body>
                    <h1>Dashboard Error</h1>
                    <p>There was an error loading the dashboard: {str(e)}</p>
                    <p>Welcome, {current_user.username}!</p>
                </body>
            </html>
            """
        )
