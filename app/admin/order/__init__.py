from fastapi import APIRouter
from fastapi.templating import Jinja2Templates
from pathlib import Path

# Create router
router = APIRouter(prefix="/admin/orders", tags=["admin_orders"])

# Setup templates
templates = Jinja2Templates(directory="app/admin/templates")

# Import routes after router and templates are defined
from app.admin.order.routes import *  # This will import all routes 
from app.admin.order.api import *  # Import API routes