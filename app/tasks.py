"""
Background tasks for the application.
This module contains tasks that run in the background at regular intervals.
"""

import asyncio
import logging
from datetime import datetime
from typing import Callable, Dict, List, Optional, Any
import time

# Configure logging
logger = logging.getLogger(__name__)

# Global registry of scheduled tasks
_tasks: Dict[str, asyncio.Task] = {}
_intervals: Dict[str, int] = {}
_last_run: Dict[str, float] = {}

async def update_bestseller_products():
    """
    Update bestseller status for all products based on sale count.
    This task identifies top-selling products and marks them as bestsellers.
    """
    try:
        from app.models.product import Product

        logger.info("Starting bestseller status update task")
        start_time = time.time()

        # Update bestseller statuses
        bestsellers_updated, non_bestsellers_updated = await Product.update_all_bestseller_statuses()

        end_time = time.time()
        duration = end_time - start_time

        logger.info(
            f"Bestseller status update completed in {duration:.2f} seconds. "
            f"Updated {bestsellers_updated} bestsellers and {non_bestsellers_updated} non-bestsellers."
        )
    except Exception as e:
        logger.error(f"Error in bestseller update task: {str(e)}")

async def update_trending_products():
    """
    Update trending status for all products based on view count.
    This task identifies products with high view counts and marks them as trending.
    """
    try:
        from app.models.product import Product
        from datetime import datetime, timedelta

        logger.info("Starting trending products update task")
        start_time = time.time()

        # Get all published products
        all_products = await Product.find({
            "status": "published",
            "$and": [
                {"name": {"$ne": "template"}},
                {"id": {"$not": {"$regex": "template", "$options": "i"}}}
            ]
        }).to_list()

        if not all_products:
            logger.info("No products found to update trending status")
            return 0, 0

        # Sort products by view_count in descending order
        all_products.sort(key=lambda p: getattr(p, "view_count", 0), reverse=True)

        # Define thresholds for trending status
        min_view_count = 1  # Minimum views to be considered trending

        # Set a fixed number of trending products (4) as requested
        trending_count = 4

        # Track counts for reporting
        updated_trending = 0
        updated_non_trending = 0

        # Update all products
        for i, product in enumerate(all_products):
            view_count = getattr(product, "view_count", 0)
            is_trending = getattr(product, "is_trending", False)

            # Determine if this product should be trending
            should_be_trending = (i < trending_count) and (view_count >= min_view_count)

            # Only update if the status needs to change
            if should_be_trending != is_trending:
                product.is_trending = should_be_trending
                await product.save()

                if should_be_trending:
                    updated_trending += 1
                    logger.debug(f"Marked as trending: {product.name} (view_count: {view_count})")
                else:
                    updated_non_trending += 1
                    logger.debug(f"Removed trending status: {product.name} (view_count: {view_count})")

        end_time = time.time()
        duration = end_time - start_time

        logger.info(
            f"Trending products update completed in {duration:.2f} seconds. "
            f"Updated {updated_trending} trending and {updated_non_trending} non-trending products."
        )

        return updated_trending, updated_non_trending
    except Exception as e:
        logger.error(f"Error in trending products update task: {str(e)}")
        return 0, 0

async def update_top_rated_products():
    """
    Update top rated status for all products based on rating average.
    This task identifies products with high ratings and marks them as top rated.
    """
    try:
        from app.models.product import Product

        logger.info("Starting top rated products update task")
        start_time = time.time()

        # Get all published products with at least one review
        all_products = await Product.find({
            "status": "published",
            "review_count": {"$gt": 0},
            "$and": [
                {"name": {"$ne": "template"}},
                {"id": {"$not": {"$regex": "template", "$options": "i"}}}
            ]
        }).to_list()

        if not all_products:
            logger.info("No products found to update top rated status")
            return 0, 0

        # Sort products by rating_avg in descending order
        all_products.sort(key=lambda p: getattr(p, "rating_avg", 0), reverse=True)

        # Define thresholds for top rated status
        min_rating = 1.0    # Minimum rating to be considered top rated
        min_reviews = 1     # Minimum number of reviews required

        # Set a fixed number of top rated products (4) as requested
        top_rated_count = 4

        # Track counts for reporting
        updated_top_rated = 0
        updated_non_top_rated = 0

        # Update all products
        for i, product in enumerate(all_products):
            rating_avg = getattr(product, "rating_avg", 0)
            review_count = getattr(product, "review_count", 0)
            is_top_rated = getattr(product, "is_top_rated", False)

            # Determine if this product should be top rated
            should_be_top_rated = (i < top_rated_count) and (rating_avg >= min_rating) and (review_count >= min_reviews)

            # Only update if the status needs to change
            if should_be_top_rated != is_top_rated:
                product.is_top_rated = should_be_top_rated
                await product.save()

                if should_be_top_rated:
                    updated_top_rated += 1
                    logger.debug(f"Marked as top rated: {product.name} (rating: {rating_avg}, reviews: {review_count})")
                else:
                    updated_non_top_rated += 1
                    logger.debug(f"Removed top rated status: {product.name} (rating: {rating_avg}, reviews: {review_count})")

        end_time = time.time()
        duration = end_time - start_time

        logger.info(
            f"Top rated products update completed in {duration:.2f} seconds. "
            f"Updated {updated_top_rated} top rated and {updated_non_top_rated} non-top rated products."
        )

        return updated_top_rated, updated_non_top_rated
    except Exception as e:
        logger.error(f"Error in top rated products update task: {str(e)}")
        return 0, 0

async def update_new_arrivals():
    """
    Update new arrivals status for all products based on creation date.
    This task identifies recently added products and marks them as new arrivals.
    """
    try:
        from app.models.product import Product
        from datetime import datetime, timedelta

        logger.info("Starting new arrivals update task")
        start_time = time.time()

        # Get all published products
        all_products = await Product.find({
            "status": "published",
            "$and": [
                {"name": {"$ne": "template"}},
                {"id": {"$not": {"$regex": "template", "$options": "i"}}}
            ]
        }).to_list()

        if not all_products:
            logger.info("No products found to update new arrivals status")
            return 0, 0

        # Sort products by creation date (newest first)
        all_products.sort(key=lambda p: getattr(p, "created_at", datetime.min), reverse=True)

        # Set a fixed number of new arrivals (4) as requested
        new_arrival_count = 4

        # Track counts for reporting
        updated_new_arrivals = 0
        updated_non_new_arrivals = 0

        # Update all products
        for i, product in enumerate(all_products):
            is_new = getattr(product, "is_new", False)

            # Determine if this product should be marked as new (top 8 newest products)
            should_be_new = i < new_arrival_count

            # Only update if the status needs to change
            if should_be_new != is_new:
                product.is_new = should_be_new
                await product.save()

                created_at = getattr(product, "created_at", None)
                if should_be_new:
                    updated_new_arrivals += 1
                    logger.debug(f"Marked as new arrival: {product.name} (created: {created_at})")
                else:
                    updated_non_new_arrivals += 1
                    logger.debug(f"Removed new arrival status: {product.name} (created: {created_at})")

        end_time = time.time()
        duration = end_time - start_time

        logger.info(
            f"New arrivals update completed in {duration:.2f} seconds. "
            f"Updated {updated_new_arrivals} new arrivals and {updated_non_new_arrivals} non-new arrivals."
        )

        return updated_new_arrivals, updated_non_new_arrivals
    except Exception as e:
        logger.error(f"Error in new arrivals update task: {str(e)}")
        return 0, 0

async def run_task_periodically(task_func: Callable, interval_seconds: int, task_name: str):
    """
    Run a task periodically at the specified interval.

    Args:
        task_func: The async function to run
        interval_seconds: The interval in seconds between task runs
        task_name: A unique name for the task
    """
    while True:
        try:
            logger.debug(f"Running scheduled task: {task_name}")
            _last_run[task_name] = time.time()
            await task_func()
        except Exception as e:
            logger.error(f"Error in scheduled task {task_name}: {str(e)}")

        # Sleep until next interval
        await asyncio.sleep(interval_seconds)

def schedule_task(task_func: Callable, interval_seconds: int, task_name: Optional[str] = None) -> str:
    """
    Schedule a task to run periodically.

    Args:
        task_func: The async function to run
        interval_seconds: The interval in seconds between task runs
        task_name: Optional name for the task (defaults to function name)

    Returns:
        The task name
    """
    task_name = task_name or task_func.__name__

    # Cancel existing task if it exists
    if task_name in _tasks and not _tasks[task_name].done():
        _tasks[task_name].cancel()

    # Create and store the new task
    _tasks[task_name] = asyncio.create_task(
        run_task_periodically(task_func, interval_seconds, task_name)
    )
    _intervals[task_name] = interval_seconds

    logger.info(f"Scheduled task '{task_name}' to run every {interval_seconds} seconds")
    return task_name

def get_task_status(task_name: str) -> Dict[str, Any]:
    """
    Get the status of a scheduled task.

    Args:
        task_name: The name of the task

    Returns:
        A dictionary with task status information
    """
    if task_name not in _tasks:
        return {"status": "not_found"}

    task = _tasks[task_name]
    interval = _intervals.get(task_name, 0)
    last_run = _last_run.get(task_name, None)

    now = time.time()
    next_run = (last_run + interval) if last_run else None
    time_until_next = (next_run - now) if next_run else None

    return {
        "status": "running" if not task.done() else "completed",
        "interval_seconds": interval,
        "last_run": datetime.fromtimestamp(last_run).isoformat() if last_run else None,
        "next_run": datetime.fromtimestamp(next_run).isoformat() if next_run else None,
        "time_until_next_run_seconds": round(time_until_next) if time_until_next else None,
        "exception": str(task.exception()) if task.done() and task.exception() else None
    }

def get_all_tasks_status() -> Dict[str, Dict[str, Any]]:
    """
    Get the status of all scheduled tasks.

    Returns:
        A dictionary mapping task names to their status information
    """
    return {task_name: get_task_status(task_name) for task_name in _tasks}

def cancel_all_tasks():
    """Cancel all scheduled tasks."""
    for task_name, task in _tasks.items():
        if not task.done():
            logger.info(f"Cancelling task: {task_name}")
            task.cancel()

    _tasks.clear()
    _intervals.clear()
    _last_run.clear()
