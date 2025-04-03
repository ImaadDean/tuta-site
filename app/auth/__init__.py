from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/auth", tags=["Auth"])
templates = Jinja2Templates(directory="app/auth/templates")

from app.auth.routers import router