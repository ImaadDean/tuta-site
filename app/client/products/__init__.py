from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["Client_Products"])
templates = Jinja2Templates(directory="app/client/templates")

from app.client.products.routes import router

