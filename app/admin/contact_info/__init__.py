from fastapi import APIRouter
from fastapi.templating import Jinja2Templates
from pathlib import Path

# Create router
router = APIRouter(prefix="/admin/contact_info", tags=["admin_contact_info"])

# Setup templates
templates = Jinja2Templates(directory="app/admin/templates")

# Import routes after router and templates are defined
from app.admin.contact_info.routes import *
from app.admin.contact_info.api import *
