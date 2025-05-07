from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.auth.routers import router as auth_router
from app.admin.dashboard import router as admin_router
from app.admin.account import router as admin_account_router
from app.admin.products import router as admin_product_router
from app.admin.banner import router as admin_banner_router
from app.admin.user import router as admin_user_router
from app.admin.order import router as admin_order_router
from app.admin.category import router as admin_category_router
from app.admin.collection import router as admin_collection_router
from app.admin.brand import router as admin_brand_router
from app.admin.scent import router as admin_scent_router
from app.admin.contact_info import router as admin_contact_info_router
from app.admin.message import router as admin_message_router
from app.database import initialize_mongodb, close_mongodb_connection, lifespan_mongodb_connection
from app.jinja_filters import setup_jinja_filters
from fastapi.templating import Jinja2Templates
import logging
from config import get_settings
from app.client.main.routes import router as client_main_router
from app.client.products import router as client_products_router
from app.client.checkout import router as client_checkout_router
from app.client.orders import router as client_orders_router
from app.client.main.api import router as client_api_router

# Configure logging
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Monkey patch Jinja2Templates to include our custom filters
original_init = Jinja2Templates.__init__

def patched_init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    setup_jinja_filters(self.env)

Jinja2Templates.__init__ = patched_init

def create_app():
    # Use the lifespan context manager for database connections
    app = FastAPI(
        title="Perfumes & More",
        lifespan=lifespan_mongodb_connection
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Configure Session Middleware
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SECRET_KEY,
        session_cookie="session",
        max_age=3600  # 1 hour
    )

    # Include the routers
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(admin_account_router)
    app.include_router(admin_product_router)
    app.include_router(admin_banner_router)
    app.include_router(admin_user_router)
    app.include_router(admin_order_router)
    app.include_router(admin_category_router)
    app.include_router(admin_collection_router)
    app.include_router(admin_brand_router)
    app.include_router(admin_scent_router)
    app.include_router(admin_contact_info_router)
    app.include_router(admin_message_router)
    app.include_router(client_main_router)
    app.include_router(client_products_router)
    app.include_router(client_checkout_router)
    app.include_router(client_orders_router)
    app.include_router(client_api_router)
    # No need for these event handlers anymore, they're handled by the lifespan
    # context manager

    return app