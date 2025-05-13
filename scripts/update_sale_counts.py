"""
Script to update product sale_count based on order history.
This script will analyze all orders and update the sale_count for each product.
"""

import asyncio
import os
import sys
from typing import Dict, List
from datetime import datetime

# Add the parent directory to the path so we can import from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.product import Product
from app.models.order import Order, OrderStatus
from app.database import init_db

async def update_sale_counts():
    """Update sale_count for all products based on order history"""
    print("Starting update of product sale_count based on order history...")

    # Initialize the database
    await init_db()

    # Get all products
    products = await Product.find_all().to_list()
    print(f"Found {len(products)} products")

    # Create a dictionary to track sale counts by product ID
    sale_counts = {}

    # Get all completed orders
    completed_orders = await Order.find(
        {"status": {"$in": [OrderStatus.COMPLETED, OrderStatus.DELIVERED]}}
    ).to_list()
    print(f"Found {len(completed_orders)} completed orders")

    # Count sales for each product
    for order in completed_orders:
        for item in order.items:
            product_id = item.product_id
            quantity = item.quantity

            if product_id not in sale_counts:
                sale_counts[product_id] = 0

            sale_counts[product_id] += quantity

    print(f"Calculated sale counts for {len(sale_counts)} products")

    # Update each product with its sale count
    updated_count = 0
    for product in products:
        if product.id in sale_counts:
            old_sale_count = getattr(product, 'sale_count', 0)
            product.sale_count = sale_counts[product.id]

            # Don't update sales_count as it doesn't exist in the model

            await product.save()
            updated_count += 1
            print(f"Updated product {product.id} - {product.name}: {old_sale_count} -> {product.sale_count}")

    print(f"Update complete. Updated {updated_count} products.")

if __name__ == "__main__":
    # Run the update
    asyncio.run(update_sale_counts())
