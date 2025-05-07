from fastapi import APIRouter
from fastapi.templating import Jinja2Templates
from pathlib import Path

# Create router
router = APIRouter(prefix="/admin/contact", tags=["admin_contact"])

# Setup templates
templates = Jinja2Templates(directory="app/admin/templates")

# Import routes after router and templates are defined
from app.admin.contact.routes import *
from app.admin.contact.api import *
