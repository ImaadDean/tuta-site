from fastapi import APIRouter
from fastapi.templating import Jinja2Templates
from pathlib import Path

# Create router
router = APIRouter(prefix="/admin/brand", tags=["admin-brand"])

# Setup templates
templates = Jinja2Templates(directory="app/admin/templates")

from app.admin.brand.routes import *
