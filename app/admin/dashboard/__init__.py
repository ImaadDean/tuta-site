from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

# Use tags instead of prefix to allow more flexibility with URL paths
router = APIRouter(prefix="/admin", tags=["Admin_dashboard"])
templates = Jinja2Templates(directory="app/admin/templates")

# Import after router is defined to avoid circular import
from app.admin.dashboard.routers import router
from app.admin.dashboard.api import router
