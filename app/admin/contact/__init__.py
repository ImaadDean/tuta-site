from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

# Use tags instead of prefix to allow more flexibility with URL paths
router = APIRouter(prefix="/admin/contact", tags=["Admin_contact"])
templates = Jinja2Templates(directory="app/admin/templates")

# Import after router is defined to avoid circular import
from app.admin.contact.routes import router
