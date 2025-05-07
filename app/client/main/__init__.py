from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["Clients_main"])
templates = Jinja2Templates(directory="app/client/templates")

from app.client.main.routes import router as main_router
from app.client.main.api import router as api_router