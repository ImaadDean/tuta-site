from motor.motor_asyncio import AsyncIOMotorClient
from config import get_settings
import logging
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, InvalidOperation
from beanie import init_beanie
import asyncio
from contextlib import asynccontextmanager

# Import all document models
from app.models.user import User
from app.models.token import PasswordResetToken
from app.models.product import Product, VariantValue
from app.models.order import Order
from app.models.category import Category
from app.models.collection import Collection
from app.models.brand import Brand
from app.models.banner import Banner
from app.models.scent import Scent
from app.models.review import Review
from app.models.address import Address

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Global variables to store MongoDB client and database
mongo_client = None
db = None

# Connection state tracking
is_closing = False
connection_lock = asyncio.Lock()

async def get_db():
    """
    Get database connection. This will ensure a connection exists before returning.
    """
    global mongo_client, db, is_closing
    
    # If we're in the process of closing, wait a moment
    if is_closing:
        await asyncio.sleep(0.1)
    
    # Use a lock to prevent multiple simultaneous initializations
    async with connection_lock:
        # Check if we need to initialize
        if db is None or mongo_client is None:
            # Create a new connection
            await initialize_mongodb()
        else:
            # Check if connection is still alive - use a safer approach
            try:
                # Use a simple synchronous check instead of asyncio.wait_for
                # This avoids potential event loop issues
                if not mongo_client.server_info():
                    logger.warning("MongoDB connection is stale or closed, reconnecting...")
                    await close_mongodb_connection()
                    await initialize_mongodb()
            except Exception:
                logger.warning("MongoDB connection check failed, reconnecting...")
                await close_mongodb_connection()
                await initialize_mongodb()
    
    return db

async def initialize_mongodb():
    """
    Initialize MongoDB connection with better error handling for traditional server environment
    """
    global mongo_client, db, is_closing
    
    # Don't initialize if we're in the process of closing
    if is_closing:
        await asyncio.sleep(0.1)
        if db is not None and mongo_client is not None:
            return db
    
    try:
        # Get MongoDB URI from settings
        mongodb_uri = settings.MONGODB_URI
        if not mongodb_uri:
            raise ValueError("MongoDB URI is not configured. Please check your environment variables.")
        
        # Standard settings for long-running server
        conn_params = {
            "serverSelectionTimeoutMS": 5000,
            "connectTimeoutMS": 5000,
            "socketTimeoutMS": 30000,
            "maxPoolSize": 50,
            "minPoolSize": 5,
            "maxIdleTimeMS": 60000,
            "waitQueueTimeoutMS": 5000,
            "heartbeatFrequencyMS": 10000,
            "retryWrites": True,
            "retryReads": True,
            "appName": "PerfumesMoreApp"
        }
        
        # Create a new client with optimized settings
        mongo_client = AsyncIOMotorClient(mongodb_uri, **conn_params)
        
        # Get database
        db = mongo_client[settings.MONGODB_DATABASE]
        
        # Initialize Beanie with all document models
        await init_beanie(
            database=db,
            document_models=[
                User,
                PasswordResetToken,
                Product,
                Order,
                Category,
                Collection,
                Brand,
                Banner,
                Scent,
                Review,
                Address
            ]
        )
        
        # Verify connection - use a safer approach
        try:
            # Use a synchronous operation instead of asyncio.wait_for
            mongo_client.admin.command('ping')
            logger.info("MongoDB connection established successfully.")
            logger.info("Beanie document models initialized successfully.")
        except Exception as e:
            logger.error(f"MongoDB connection verification failed: {str(e)}")
            raise
        
        return db
    except Exception as e:
        logger.error(f"Failed to initialize MongoDB connection: {str(e)}")
        if mongo_client:
            mongo_client.close()
            mongo_client = None
            db = None
        raise

async def close_mongodb_connection():
    """
    Close MongoDB connection more safely
    """
    global mongo_client, db, is_closing
    
    # Set closing flag to prevent new connections during shutdown
    is_closing = True
    
    try:
        if mongo_client:
            try:
                logger.debug("Closing MongoDB connection.")
                mongo_client.close()
            except Exception as e:
                logger.error(f"Error closing MongoDB connection: {str(e)}")
    finally:
        # Clear global references
        mongo_client = None
        db = None
        is_closing = False

# For use with FastAPI lifespan context manager
@asynccontextmanager
async def lifespan_mongodb_connection(app):
    """
    Lifespan context manager for FastAPI to properly handle MongoDB connections
    """
    try:
        await initialize_mongodb()
        yield
    finally:
        await close_mongodb_connection()