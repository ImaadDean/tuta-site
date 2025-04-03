from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/admin/products", tags=["Admin_product"])
templates = Jinja2Templates(directory="app/admin/templates")

from app.admin.products.routes import router
