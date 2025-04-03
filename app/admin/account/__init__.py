from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/admin/account", tags=["Admin_Account"])
templates = Jinja2Templates(directory="app/admin/templates")

from app.admin.account.routers import router 