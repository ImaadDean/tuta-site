from pydantic_settings import BaseSettings
from pydantic import EmailStr
import cloudinary
import secrets
from fastapi_mail import ConnectionConfig
import os

class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "production"

    # Session settings
    SECRET_KEY: str = secrets.token_hex(32)

    # Email settings
    MAIL_USERNAME: str = "perfumesandmore.ug@gmail.com"
    MAIL_PASSWORD: str = "vlaj owhi pgvt bwij"
    MAIL_FROM: str = "Perfumes & More"
    MAIL_PORT: int = 587
    MAIL_SERVER: str = "smtp.gmail.com"
    MAIL_TLS: bool = True
    MAIL_SSL: bool = False
    USE_CREDENTIALS: bool = True

    # MongoDB settings
    MONGO_USERNAME: str = "imaad"
    MONGO_PASSWORD: str = "Ertdfgxc"
    MONGO_HOST: str = "129.80.199.242"
    MONGO_PORT: int = 27017
    MONGO_DATABASE: str = "perfumes_more"
    MONGO_POOL_SIZE: int = 20

    # New MongoDB URI setting
    MONGODB_URI: str = ""
    MONGODB_DATABASE: str = "perfumes_more"

    # Database connection pool settings
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 0
    DB_POOL_PRE_PING: bool = True
    DB_POOL_USE_LIFO: bool = True
    DB_STATEMENT_TIMEOUT: int = 60000
    DB_IDLE_TIMEOUT: int = 60000

    # Cloudinary settings
    CLOUDINARY_CLOUD_NAME: str = "dqgbwjapm"
    CLOUDINARY_API_KEY: str = "435261214334877"
    CLOUDINARY_API_SECRET: str = "e45s-2zVcCIJMV_vv-N-_PJcvZI"
    CLOUDINARY_BASE_FOLDER: str = "perfumes_and_more"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"

def get_settings():
    settings = Settings()

    # Configure Cloudinary
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET
    )

    # Configure FastMail
    settings.mail_config = ConnectionConfig(
        MAIL_USERNAME=settings.MAIL_USERNAME,
        MAIL_PASSWORD=settings.MAIL_PASSWORD,
        MAIL_FROM=settings.MAIL_USERNAME,
        MAIL_PORT=settings.MAIL_PORT,
        MAIL_SERVER=settings.MAIL_SERVER,
        MAIL_FROM_NAME=settings.MAIL_FROM,
        MAIL_STARTTLS=settings.MAIL_TLS,
        MAIL_SSL_TLS=settings.MAIL_SSL,
        USE_CREDENTIALS=settings.USE_CREDENTIALS,
        VALIDATE_CERTS=True,
    )

    # Create MongoDB URI if not provided
    if not settings.MONGODB_URI:
        # Try with authSource parameter
        settings.MONGODB_URI = f"mongodb://{settings.MONGO_USERNAME}:{settings.MONGO_PASSWORD}@{settings.MONGO_HOST}:{settings.MONGO_PORT}/?authSource=admin"
        settings.MONGODB_DATABASE = settings.MONGO_DATABASE

    # Log the environment type
    print(f"Running in {settings.ENVIRONMENT} environment")

    return settings

# Create a global instance of settings
settings = get_settings()


