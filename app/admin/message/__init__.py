from fastapi import APIRouter
from fastapi.templating import Jinja2Templates
from pathlib import Path

# Create router
router = APIRouter(prefix="/admin/message", tags=["admin_message"])

# Setup templates
templates = Jinja2Templates(directory="app/admin/templates")

# Import routes after router and templates are defined
from app.admin.message.routes import *
from app.admin.message.api import *
