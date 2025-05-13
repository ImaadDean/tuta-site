"""
Migration script to update products with sales_count to use sale_count.
This script should be run once to ensure all existing products have the correct sale_count field.
"""

import asyncio
import os
import sys
from typing import List, Dict, Any

# Add the parent directory to the path so we can import from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.product import Product
from app.database import init_db

async def migrate_sales_count():
    """Migrate sales_count to sale_count for all products"""
    print("Starting migration of sales_count to sale_count...")
    
    # Initialize the database
    await init_db()
    
    # Get all products
    products = await Product.find_all().to_list()
    print(f"Found {len(products)} products to check")
    
    updated_count = 0
    
    for product in products:
        # Check if product has sales_count but not sale_count
        sales_count = getattr(product, 'sales_count', 0)
        sale_count = getattr(product, 'sale_count', 0)
        
        if sales_count > 0 and sale_count == 0:
            # Update sale_count to match sales_count
            product.sale_count = sales_count
            await product.save()
            updated_count += 1
            print(f"Updated product {product.id} - {product.name}: sales_count={sales_count} -> sale_count={product.sale_count}")
    
    print(f"Migration complete. Updated {updated_count} products.")

if __name__ == "__main__":
    # Run the migration
    asyncio.run(migrate_sales_count())
