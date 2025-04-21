from datetime import datetime, date
import json
from bson import ObjectId
from uuid import UUID
from jinja2 import pass_context

def datetime_serializer(obj):
    """
    Custom serializer for datetime and date objects.
    """
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

def tojson_filter(obj):
    """Custom JSON filter that handles special types like ObjectId, datetime, UUID."""
    def json_serializer(obj):
        """Helper function to serialize objects that aren't serializable by default."""
        if isinstance(obj, (ObjectId, UUID)):
            return str(obj)
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            # Handle nested dictionaries
            return {k: json_serializer(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            # Handle lists of objects
            return [json_serializer(item) for item in obj]
        elif hasattr(obj, 'dict'):
            # Handle Pydantic/Beanie models
            return json_serializer(obj.dict())
        elif hasattr(obj, '__dict__'):
            # Handle generic objects
            return json_serializer(obj.__dict__)
        return obj
    
    try:
        # First serialize the object to handle nested structures 
        serialized_obj = json_serializer(obj)
        # Then convert to JSON string
        return json.dumps(serialized_obj)
    except TypeError as e:
        print(f"Error serializing object: {e}")
        return json.dumps(str(obj))

@pass_context
def format_currency(context, value):
    """Format a number as currency with commas."""
    if value is None:
        return "0"
    return "{:,}".format(value)

def setup_jinja_filters(env):
    """
    Register custom filters with a Jinja2 environment
    """
    # Override the built-in tojson filter with our custom one
    env.filters["tojson"] = tojson_filter
    env.filters["currency"] = format_currency
    env.filters["custom_tojson"] = tojson_filter 