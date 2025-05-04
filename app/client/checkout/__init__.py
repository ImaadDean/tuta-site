from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["Clients_main"])
templates = Jinja2Templates(directory="app/client/templates")

from app.client.checkout.routes import router
from app.client.checkout.api import router