from fastapi import APIRouter
from fastapi.templating import Jinja2Templates


router = APIRouter(prefix="/admin/collection", tags=["admin_category"])

templates = Jinja2Templates(directory="app/admin/templates")

from app.admin.collection.routes import * 