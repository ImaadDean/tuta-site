"""
Script to update product flags (is_trending, is_top_rated, is_bestseller, is_new) in the database.
Run this script to manually update these flags without waiting for the scheduled tasks.
"""

import asyncio
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Main function to run all update tasks"""
    try:
        # Import tasks here to avoid circular imports
        from app.database import initialize_mongodb, close_mongodb_connection
        from app.tasks import (
            update_bestseller_products,
            update_trending_products,
            update_top_rated_products,
            update_new_arrivals
        )
        
        # Initialize database connection
        logger.info("Initializing database connection...")
        await initialize_mongodb()
        
        # Update trending products
        logger.info("Updating trending products...")
        start_time = datetime.now()
        await update_trending_products()
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Trending products updated in {duration:.2f} seconds")
        
        # Update top rated products
        logger.info("Updating top rated products...")
        start_time = datetime.now()
        await update_top_rated_products()
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Top rated products updated in {duration:.2f} seconds")
        
        # Update bestseller products
        logger.info("Updating bestseller products...")
        start_time = datetime.now()
        await update_bestseller_products()
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Bestseller products updated in {duration:.2f} seconds")
        
        # Update new arrivals
        logger.info("Updating new arrivals...")
        start_time = datetime.now()
        await update_new_arrivals()
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"New arrivals updated in {duration:.2f} seconds")
        
        # Close database connection
        logger.info("Closing database connection...")
        await close_mongodb_connection()
        
        logger.info("All product flags updated successfully!")
    except Exception as e:
        logger.error(f"Error updating product flags: {str(e)}")
        raise

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
