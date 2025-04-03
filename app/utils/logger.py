import logging
import sys
from datetime import datetime

# Configure logging to only use console output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('app')

def log_error(message: str):
    """Log an error message"""
    logger.error(message)

def log_info(message: str):
    """Log an info message"""
    logger.info(message)

def log_warning(message: str):
    """Log a warning message"""
    logger.warning(message)

def log_debug(message: str):
    """Log a debug message"""
    logger.debug(message) 