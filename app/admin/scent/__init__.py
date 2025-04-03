from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/admin/scent", tags=["admin-scent"]) 

# Initialize templates
templates = Jinja2Templates(directory="app/admin/templates")

from app.admin.scent.routes import *
