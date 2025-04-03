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
from app.database import initialize_mongodb, close_mongodb_connection
import logging
from config import get_settings

# Configure logging
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

def create_app():
    app = FastAPI(title="Perfumes & More")
    
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
    # Setup startup and shutdown events
    @app.on_event("startup")
    async def startup_db_client():
        await initialize_mongodb()
    
    @app.on_event("shutdown")
    async def shutdown_db_client():
        await close_mongodb_connection()
    
    return app