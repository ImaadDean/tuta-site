"""
Script to manually set product flags (is_trending, is_top_rated, is_bestseller, is_new) for specific products.
Use this script to override the automatic flag settings for individual products.
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

async def set_product_flag(product_id, flag_name, flag_value):
    """Set a specific flag for a product"""
    try:
        # Import models here to avoid circular imports
        from app.database import initialize_mongodb, close_mongodb_connection
        from app.models.product import Product
        
        # Initialize database connection
        logger.info("Initializing database connection...")
        await initialize_mongodb()
        
        # Find the product
        product = await Product.find_one({"$or": [{"id": product_id}, {"_id": product_id}]})
        if not product:
            logger.error(f"Product with ID {product_id} not found")
            return False
        
        # Set the flag
        old_value = getattr(product, flag_name, None)
        setattr(product, flag_name, flag_value)
        
        # Save the product
        await product.save()
        
        logger.info(f"Updated product '{product.name}' ({product_id}): {flag_name} changed from {old_value} to {flag_value}")
        
        # Close database connection
        logger.info("Closing database connection...")
        await close_mongodb_connection()
        
        return True
    except Exception as e:
        logger.error(f"Error setting product flag: {str(e)}")
        return False

async def list_products(filter_criteria=None, limit=10):
    """List products with optional filtering"""
    try:
        # Import models here to avoid circular imports
        from app.database import initialize_mongodb, close_mongodb_connection
        from app.models.product import Product
        
        # Initialize database connection
        logger.info("Initializing database connection...")
        await initialize_mongodb()
        
        # Build query
        query = {
            "status": "published",
            "$and": [
                {"name": {"$ne": "template"}},
                {"id": {"$not": {"$regex": "template", "$options": "i"}}}
            ]
        }
        
        # Add filter criteria if provided
        if filter_criteria:
            query.update(filter_criteria)
        
        # Find products
        products = await Product.find(query).limit(limit).to_list()
        
        # Print products
        print(f"\nFound {len(products)} products:")
        print("-" * 80)
        for product in products:
            print(f"ID: {product.id}")
            print(f"Name: {product.name}")
            print(f"View Count: {product.view_count}")
            print(f"Rating Avg: {product.rating_avg}")
            print(f"Sale Count: {product.sale_count}")
            print(f"Flags: is_trending={product.is_trending}, is_top_rated={product.is_top_rated}, "
                  f"is_bestseller={product.is_bestseller}, is_new={product.is_new}")
            print("-" * 80)
        
        # Close database connection
        logger.info("Closing database connection...")
        await close_mongodb_connection()
        
        return True
    except Exception as e:
        logger.error(f"Error listing products: {str(e)}")
        return False

async def main():
    """Main function to parse arguments and run the appropriate command"""
    parser = argparse.ArgumentParser(description="Manually set product flags")
    
    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Set flag command
    set_parser = subparsers.add_parser("set", help="Set a flag for a product")
    set_parser.add_argument("product_id", help="ID of the product to update")
    set_parser.add_argument("flag", choices=["is_trending", "is_top_rated", "is_bestseller", "is_new"], 
                           help="Flag to set")
    set_parser.add_argument("value", choices=["true", "false"], help="Value to set (true/false)")
    
    # List products command
    list_parser = subparsers.add_parser("list", help="List products")
    list_parser.add_argument("--limit", type=int, default=10, help="Maximum number of products to list")
    list_parser.add_argument("--trending", action="store_true", help="List trending products")
    list_parser.add_argument("--top-rated", action="store_true", help="List top rated products")
    list_parser.add_argument("--bestseller", action="store_true", help="List bestseller products")
    list_parser.add_argument("--new", action="store_true", help="List new products")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Run the appropriate command
    if args.command == "set":
        # Convert string value to boolean
        value = args.value.lower() == "true"
        success = await set_product_flag(args.product_id, args.flag, value)
        return 0 if success else 1
    
    elif args.command == "list":
        # Build filter criteria
        filter_criteria = {}
        if args.trending:
            filter_criteria["is_trending"] = True
        if args.top_rated:
            filter_criteria["is_top_rated"] = True
        if args.bestseller:
            filter_criteria["is_bestseller"] = True
        if args.new:
            filter_criteria["is_new"] = True
        
        success = await list_products(filter_criteria, args.limit)
        return 0 if success else 1
    
    else:
        parser.print_help()
        return 1

if __name__ == "__main__":
    # Run the async main function
    exit_code = asyncio.run(main())
    exit(exit_code)
