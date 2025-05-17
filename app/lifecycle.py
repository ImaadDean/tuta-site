"""
Application lifecycle management.
This module handles the FastAPI application lifecycle, including startup and shutdown events.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Callable, Dict, Any

from app.database import initialize_mongodb, close_mongodb_connection
from app.tasks import (
    schedule_task, cancel_all_tasks, 
    update_bestseller_products,
    update_trending_products,
    update_top_rated_products,
    update_new_arrivals
)

# Configure logging
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app):
    """
    Lifespan context manager for FastAPI to handle startup and shutdown events.
    This manages both database connections and background tasks.
    """
    try:
        # Initialize database connection
        await initialize_mongodb()
        
        # Schedule background tasks
        logger.info("Starting background tasks...")
        
        # Update bestseller products every 6 hours (21600 seconds)
        schedule_task(update_bestseller_products, interval_seconds=21600, task_name="update_bestsellers")
        
        # Update trending products every 12 hours (43200 seconds)
        schedule_task(update_trending_products, interval_seconds=43200, task_name="update_trending")
        
        # Update top rated products every 24 hours (86400 seconds)
        schedule_task(update_top_rated_products, interval_seconds=86400, task_name="update_top_rated")
        
        # Update new arrivals every 24 hours (86400 seconds)
        schedule_task(update_new_arrivals, interval_seconds=86400, task_name="update_new_arrivals")
        
        # Run the initial updates
        asyncio.create_task(update_bestseller_products())
        asyncio.create_task(update_trending_products())
        asyncio.create_task(update_top_rated_products())
        asyncio.create_task(update_new_arrivals())
        
        yield
    finally:
        # Cancel all background tasks
        logger.info("Shutting down background tasks...")
        cancel_all_tasks()
        
        # Close database connection
        await close_mongodb_connection()
