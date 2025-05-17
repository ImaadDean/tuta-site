# Scheduled Tasks

This directory contains scheduled tasks that should be run periodically to maintain the application's data integrity and performance.

## Bestseller Updater

The `bestseller_updater.py` script updates the bestseller status of products based on their sale count. Products with the highest sale counts are marked as bestsellers, which affects how they are displayed in the UI.

### How It Works

The script:
1. Retrieves all published products
2. Sorts them by sale count in descending order
3. Marks the top 10% of products as bestsellers (with a minimum sale count threshold of 5)
4. Updates the `is_bestseller` flag in the database

### Running the Task

You can run the task manually:

```bash
python -m app.tasks.bestseller_updater
```

### Scheduling the Task

#### On Linux/macOS (using cron)

1. Open your crontab file:
   ```bash
   crontab -e
   ```

2. Add a line to run the task daily at midnight:
   ```
   0 0 * * * cd /path/to/your/app && python -m app.tasks.bestseller_updater >> /path/to/logs/bestseller_updater.log 2>&1
   ```

#### On Windows (using Task Scheduler)

1. Open Task Scheduler
2. Create a new Basic Task:
   - Name: "Update Bestseller Products"
   - Trigger: Daily at midnight
   - Action: Start a program
   - Program/script: `python`
   - Arguments: `-m app.tasks.bestseller_updater`
   - Start in: `C:\path\to\your\app`

### Configuration

You can adjust the bestseller criteria by modifying the following parameters in the `update_all_bestseller_statuses` method in `app/models/product.py`:

- `min_sale_count`: Minimum number of sales required to be considered a bestseller (default: 5)
- `top_percent`: Percentage of top-selling products to mark as bestsellers (default: 0.10 or 10%)

## Other Tasks

Add documentation for other scheduled tasks here as they are implemented.
