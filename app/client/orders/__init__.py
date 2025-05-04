from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["Client_Orders"])
templates = Jinja2Templates(directory="app/client/templates")

from app.client.orders.routes import router
from app.client.orders.api import router

