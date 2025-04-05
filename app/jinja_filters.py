from datetime import datetime, date
import json

def datetime_serializer(obj):
    """
    Custom serializer for datetime and date objects.
    """
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

def tojson_filter(value):
    """
    Custom JSON filter for Jinja2 that handles datetime objects.
    """
    return json.dumps(value, default=datetime_serializer)

def setup_jinja_filters(env):
    """
    Register custom filters with a Jinja2 environment
    """
    # Override the built-in tojson filter with our custom one
    env.filters["tojson"] = tojson_filter 