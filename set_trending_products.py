"""
Script to set specific products as trending or top-rated.
This script allows you to manually set products as trending or top-rated based on criteria.
"""

import asyncio
import logging
import argparse
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def set_trending_products(count=4, by_views=True):
    """Set the top N products as trending based on view count"""
    try:
        # Import models here to avoid circular imports
        from app.database import initialize_mongodb, close_mongodb_connection
        from app.models.product import Product
        
        # Initialize database connection
        logger.info("Initializing database connection...")
        await initialize_mongodb()
        
        # Reset all products first
        logger.info("Resetting trending flag for all products...")
        await Product.find({}).update_many({"$set": {"is_trending": False}})
        
        # Find products to mark as trending
        query = {
            "status": "published",
            "$and": [
                {"name": {"$ne": "template"}},
                {"id": {"$not": {"$regex": "template", "$options": "i"}}}
            ]
        }
        
        if by_views:
            # Sort by view count (descending)
            logger.info(f"Finding top {count} products by view count...")
            products = await Product.find(query).sort([("view_count", -1)]).limit(count).to_list()
        else:
            # Get the most recently created products
            logger.info(f"Finding top {count} products by creation date...")
            products = await Product.find(query).sort([("created_at", -1)]).limit(count).to_list()
        
        # Mark products as trending
        for product in products:
            product.is_trending = True
            product.updated_at = datetime.now()
            await product.save()
            logger.info(f"Marked product '{product.name}' as trending (view count: {product.view_count})")
        
        logger.info(f"Set {len(products)} products as trending")
        
        # Close database connection
        logger.info("Closing database connection...")
        await close_mongodb_connection()
        
        return len(products)
    except Exception as e:
        logger.error(f"Error setting trending products: {str(e)}")
        raise

async def set_top_rated_products(count=4):
    """Set the top N products as top-rated based on rating average"""
    try:
        # Import models here to avoid circular imports
        from app.database import initialize_mongodb, close_mongodb_connection
        from app.models.product import Product
        
        # Initialize database connection
        logger.info("Initializing database connection...")
        await initialize_mongodb()
        
        # Reset all products first
        logger.info("Resetting top-rated flag for all products...")
        await Product.find({}).update_many({"$set": {"is_top_rated": False}})
        
        # Find products to mark as top-rated
        query = {
            "status": "published",
            "rating_avg": {"$gt": 0},  # Only include products with ratings
            "review_count": {"$gt": 0},  # Only include products with reviews
            "$and": [
                {"name": {"$ne": "template"}},
                {"id": {"$not": {"$regex": "template", "$options": "i"}}}
            ]
        }
        
        # Sort by rating average (descending) and then by review count (descending)
        logger.info(f"Finding top {count} products by rating...")
        products = await Product.find(query).sort([("rating_avg", -1), ("review_count", -1)]).limit(count).to_list()
        
        # Mark products as top-rated
        for product in products:
            product.is_top_rated = True
            product.updated_at = datetime.now()
            await product.save()
            logger.info(f"Marked product '{product.name}' as top-rated (rating: {product.rating_avg}, reviews: {product.review_count})")
        
        logger.info(f"Set {len(products)} products as top-rated")
        
        # Close database connection
        logger.info("Closing database connection...")
        await close_mongodb_connection()
        
        return len(products)
    except Exception as e:
        logger.error(f"Error setting top-rated products: {str(e)}")
        raise

async def main():
    """Main function to parse arguments and run the appropriate command"""
    parser = argparse.ArgumentParser(description="Set trending and top-rated products")
    
    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Trending command
    trending_parser = subparsers.add_parser("trending", help="Set trending products")
    trending_parser.add_argument("--count", type=int, default=4, help="Number of products to mark as trending")
    trending_parser.add_argument("--by-date", action="store_true", help="Sort by creation date instead of view count")
    
    # Top-rated command
    top_rated_parser = subparsers.add_parser("top-rated", help="Set top-rated products")
    top_rated_parser.add_argument("--count", type=int, default=4, help="Number of products to mark as top-rated")
    
    # Both command
    both_parser = subparsers.add_parser("both", help="Set both trending and top-rated products")
    both_parser.add_argument("--count", type=int, default=4, help="Number of products to mark for each category")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Run the appropriate command
    if args.command == "trending":
        count = await set_trending_products(args.count, not args.by_date)
        return 0 if count > 0 else 1
    
    elif args.command == "top-rated":
        count = await set_top_rated_products(args.count)
        return 0 if count > 0 else 1
    
    elif args.command == "both":
        trending_count = await set_trending_products(args.count)
        top_rated_count = await set_top_rated_products(args.count)
        return 0 if trending_count > 0 and top_rated_count > 0 else 1
    
    else:
        parser.print_help()
        return 1

if __name__ == "__main__":
    # Run the async main function
    exit_code = asyncio.run(main())
    exit(exit_code)
