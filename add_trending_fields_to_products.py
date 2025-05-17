"""
Migration script to add is_trending and is_top_rated fields to existing products.
This script will update all products in the database to set these fields to False by default.
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

async def add_trending_fields_to_products():
    """Add is_trending and is_top_rated fields to all existing products"""
    try:
        # Import models here to avoid circular imports
        from app.database import initialize_mongodb, close_mongodb_connection
        from app.models.product import Product
        
        # Initialize database connection
        logger.info("Initializing database connection...")
        await initialize_mongodb()
        
        # Get all products
        logger.info("Fetching all products...")
        products = await Product.find({}).to_list()
        logger.info(f"Found {len(products)} products")
        
        # Update products
        updated_count = 0
        for product in products:
            # Check if fields already exist
            needs_update = False
            
            if not hasattr(product, 'is_trending') or product.is_trending is None:
                product.is_trending = False
                needs_update = True
                
            if not hasattr(product, 'is_top_rated') or product.is_top_rated is None:
                product.is_top_rated = False
                needs_update = True
            
            # Save product if it needs updating
            if needs_update:
                product.updated_at = datetime.now()
                await product.save()
                updated_count += 1
                
        logger.info(f"Updated {updated_count} products with trending fields")
        
        # Close database connection
        logger.info("Closing database connection...")
        await close_mongodb_connection()
        
        return updated_count
    except Exception as e:
        logger.error(f"Error adding trending fields to products: {str(e)}")
        raise

async def main():
    """Main function to run the migration"""
    try:
        updated_count = await add_trending_fields_to_products()
        logger.info(f"Migration completed successfully. Updated {updated_count} products.")
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        raise

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
