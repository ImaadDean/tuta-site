from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

# Create router for HTML routes
router = APIRouter(prefix="/categories", tags=["client_category"])
templates = Jinja2Templates(directory="app/client/templates")

# Import routes
from app.client.category.routes import *
from app.client.category.api import *
