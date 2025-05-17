"""
Scheduled task to update bestseller status for products.
This script can be run periodically (e.g., daily) to refresh bestseller statuses.

Usage:
    - Run directly: python -m app.tasks.bestseller_updater
    - Schedule with cron or Windows Task Scheduler to run daily
"""

import asyncio
import logging
from datetime import datetime

from app.models.product import Product
from app.database import initialize_mongodb, close_mongodb_connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

async def update_bestseller_statuses():
    """Update bestseller status for all products based on sale_count"""
    try:
        # Initialize MongoDB connection
        await initialize_mongodb()

        # Log start time
        start_time = datetime.now()
        logger.info(f"Starting bestseller status update at {start_time}")

        # Call the update method from the Product model
        bestsellers_count, non_bestsellers_count = await Product.update_all_bestseller_statuses()

        # Log completion
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"Bestseller status update completed in {duration:.2f} seconds")
        logger.info(f"Updated {bestsellers_count} bestsellers and {non_bestsellers_count} non-bestsellers")

    except Exception as e:
        logger.error(f"Error in bestseller status update: {str(e)}")
    finally:
        # Close MongoDB connection
        await close_mongodb_connection()

if __name__ == "__main__":
    # Run the async function
    asyncio.run(update_bestseller_statuses())
