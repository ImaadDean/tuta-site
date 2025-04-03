from motor.motor_asyncio import AsyncIOMotorClient
from config import get_settings
import logging
from pymongo.errors import ConnectionFailure
from beanie import init_beanie
import asyncio
# Import all document models
from app.models.user import User
from app.models.token import PasswordResetToken
from app.models.product import Product
from app.models.order import Order
from app.models.category import Category
from app.models.collection import Collection
from app.models.brand import Brand
from app.models.banner import Banner
from app.models.scent import Scent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# MongoDB client
mongodb_client = None
db = None

async def initialize_mongodb():
    """Initialize MongoDB connection."""
    global mongodb_client, db
    
    try:
        # Create MongoDB connection string
        connection_string = f"mongodb+srv://{settings.MONGO_USERNAME}:{settings.MONGO_PASSWORD}@{settings.MONGO_HOST}/{settings.MONGO_DATABASE}?retryWrites=true&w=majority"
        
        # Create async MongoDB client
        mongodb_client = AsyncIOMotorClient(
            connection_string,
            maxPoolSize=settings.MONGO_POOL_SIZE,
            serverSelectionTimeoutMS=5000,
            appname="perfumes_more_app"
        )
        
        # Check connection
        await mongodb_client.admin.command('ping')
        
        # Get database
        db = mongodb_client[settings.MONGO_DATABASE]
        
        logger.info("MongoDB connection established successfully.")
        
        # Initialize Beanie with document models
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
                Scent
            ]
        )
        logger.info("Beanie document models initialized successfully.")
        
        return db
        
    except ConnectionFailure as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise
    except Exception as e:
        logger.error(f"Error initializing MongoDB: {e}")
        raise

async def close_mongodb_connection():
    """Close MongoDB connection."""
    global mongodb_client
    if mongodb_client:
        mongodb_client.close()
        logger.info("MongoDB connection closed.")

# Dependency to get database
async def get_db():
    """Dependency to provide a MongoDB database."""
    global db
    if db is None:
        db = await initialize_mongodb()
    return db