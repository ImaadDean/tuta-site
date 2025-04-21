from motor.motor_asyncio import AsyncIOMotorClient
from config import get_settings
import logging
from pymongo.errors import ConnectionFailure
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

# Serverless environment flag
is_serverless = settings.ENVIRONMENT == 'production'

async def get_db():
    """
    Get database connection. This will ensure a connection exists before returning.
    For serverless environments, this will create a new connection for each request.
    """
    global mongo_client, db
    
    # In serverless environments, create a fresh connection for each request
    if is_serverless or db is None:
        # Close any existing connection before creating a new one
        if mongo_client is not None and is_serverless:
            await close_mongodb_connection()
        
        # Create a new connection
        await initialize_mongodb()
    
    return db

async def initialize_mongodb():
    """
    Initialize MongoDB connection with better error handling and serverless environment support
    """
    global mongo_client, db
    
    try:
        # If client already exists and we're not in a serverless environment, return the existing connection
        if mongo_client is not None and not is_serverless:
            return db
            
        # Get MongoDB URI from settings
        mongodb_uri = settings.MONGODB_URI
        if not mongodb_uri:
            raise ValueError("MongoDB URI is not configured. Please check your environment variables.")
        
        # Create a new client with optimized settings for serverless
        if is_serverless:
            # Serverless-optimized settings: lower timeouts and fewer connections
            mongo_client = AsyncIOMotorClient(
                mongodb_uri,
                serverSelectionTimeoutMS=3000,  # 3 seconds timeout for server selection
                connectTimeoutMS=3000,          # 3 seconds timeout for initial connection
                socketTimeoutMS=10000,          # 10 seconds timeout for socket operations
                maxPoolSize=5,                  # Smaller pool for serverless
                minPoolSize=0,                  # No minimum connections for serverless
                maxIdleTimeMS=5000,             # Close idle connections sooner
                waitQueueTimeoutMS=3000,        # Shorter wait queue timeout
                retryWrites=True                # Enable retry writes for better resilience
            )
        else:
            # Standard settings for long-running server
            mongo_client = AsyncIOMotorClient(
                mongodb_uri,
                serverSelectionTimeoutMS=5000,  # 5 seconds timeout for server selection
                connectTimeoutMS=5000,          # 5 seconds timeout for initial connection
                socketTimeoutMS=30000,          # 30 seconds timeout for socket operations
                maxPoolSize=10,                 # Set max connection pool size
                minPoolSize=1,                  # Maintain at least one connection
                maxIdleTimeMS=30000,            # Close idle connections after 30 seconds
                waitQueueTimeoutMS=5000,        # Wait queue timeout
                heartbeatFrequencyMS=10000      # Check server health every 10 seconds
            )
        
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
        
        # Only verify connection if not in serverless mode
        if not is_serverless:
            await mongo_client.admin.command('ping')
            logger.info("MongoDB connection established successfully.")
            logger.info("Beanie document models initialized successfully.")
        
        return db
    except Exception as e:
        logger.error(f"Failed to initialize MongoDB connection: {str(e)}")
        if mongo_client:
            await close_mongodb_connection()
            mongo_client = None
            db = None
        raise

async def close_mongodb_connection():
    """
    Close MongoDB connection more safely
    """
    global mongo_client, db
    
    if mongo_client:
        try:
            logger.debug("Closing MongoDB connection.")
            mongo_client.close()
        except Exception as e:
            logger.error(f"Error closing MongoDB connection: {str(e)}")
    
    # Clear global references
    mongo_client = None
    db = None

# For use with FastAPI lifespan context manager
@asynccontextmanager
async def lifespan_mongodb_connection(app):
    """
    Lifespan context manager for FastAPI to properly handle MongoDB connections
    In serverless environments, this is less important as connections are per-request
    """
    if is_serverless:
        # In serverless, we don't maintain connections across requests
        yield
    else:
        # In standard environments, maintain connections for the app lifecycle
        try:
            await initialize_mongodb()
            yield
        finally:
            await close_mongodb_connection()