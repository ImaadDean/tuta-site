from functools import wraps
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Simple in-memory cache
_CACHE = {}

def clear_cache(prefix: str = None):
    """
    Clear all cache entries or entries with a specific prefix
    
    Args:
        prefix: Optional prefix to filter which cache entries to clear
    """
    if prefix:
        keys_to_remove = [key for key in _CACHE.keys() if key.startswith(prefix)]
        for key in keys_to_remove:
            _CACHE.pop(key, None)
        logger.debug(f"Cleared {len(keys_to_remove)} cache entries with prefix '{prefix}'")
    else:
        count = len(_CACHE)
        _CACHE.clear()
        logger.debug(f"Cleared all {count} cache entries")

def timed_cache(seconds: int = 60):
    """
    Simple time-based cache decorator for async functions
    
    Args:
        seconds: Number of seconds to cache the result
        
    Returns:
        Decorated function with caching
    """
    def wrapper_cache(func):
        cache = {}
        expiration = datetime.now() + timedelta(seconds=seconds)

        @wraps(func)
        async def wrapped_func(*args, **kwargs):
            nonlocal expiration

            # Check if cache needs to be cleared
            if datetime.now() > expiration:
                cache.clear()
                expiration = datetime.now() + timedelta(seconds=seconds)

            # Create a key from the function arguments
            key_parts = [func.__name__]
            # Add positional args to key
            key_parts.extend([str(arg) for arg in args])
            # Add keyword args to key (sorted to ensure consistent order)
            key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
            key = ":".join(key_parts)

            # Return cached result if available
            if key in cache:
                logger.debug(f"Cache hit for {func.__name__}")
                return cache[key]

            # Call the original function and cache the result
            result = await func(*args, **kwargs)
            cache[key] = result
            logger.debug(f"Cache miss for {func.__name__}, stored result")
            return result

        return wrapped_func
    return wrapper_cache
