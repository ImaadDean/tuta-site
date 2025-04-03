from fastapi import APIRouter
from fastapi.templating import Jinja2Templates
from pathlib import Path

# Create router
router = APIRouter(prefix="/admin/banner", tags=["admin-banner"])

templates = Jinja2Templates(directory="app/admin/templates")
# Import routes after router and templates are defined
from app.admin.banner.routes import *  # This will import all routes 