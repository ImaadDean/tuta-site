from fastapi import APIRouter
from fastapi.templating import Jinja2Templates
from pathlib import Path

# Create router
router = APIRouter(prefix="/admin/category", tags=["admin_category"])

# Setup templates
templates = Jinja2Templates(directory="app/admin/templates")

# Import routes after router and templates are defined
from app.admin.category.routes import *  # This will import all routes 