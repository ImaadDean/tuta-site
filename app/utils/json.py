import json
from datetime import datetime, date
from bson import ObjectId

def datetime_serializer(obj):
    """
    Custom serializer for datetime and date objects.
    """
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, ObjectId):
        return str(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

def dumps(obj, **kwargs):
    """
    Wrapper for json.dumps that includes the datetime serializer.
    """
    return json.dumps(obj, default=datetime_serializer, **kwargs)

def safe_dict_conversion(obj):
    """
    Safely convert an object to a dict, handling cases where the object
    might be an iterable of tuples but some tuples don't have exactly 2 elements.
    """
    if isinstance(obj, dict):
        return obj.copy()
    
    # Try to treat it as an iterable of key-value pairs
    result = {}
    try:
        for item in obj:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                # Take only first two elements as key-value
                result[item[0]] = item[1]
            elif hasattr(item, '__iter__') and not isinstance(item, (str, bytes)):
                # If item is itself iterable but not a string, try to get first two elements
                iterator = iter(item)
                key = next(iterator, None)
                value = next(iterator, None)
                if key is not None:  # Accept None as a value but not as a key
                    result[key] = value
    except (TypeError, ValueError):
        # If it fails as an iterable, try other methods
        pass
        
    # If we got an empty result and obj is not empty, try other methods
    if not result and obj:
        # Try __dict__ if available
        if hasattr(obj, '__dict__'):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
            
    return result

def to_serializable_dict(obj):
    """
    Convert a model instance or dictionary to a fully serializable dictionary.
    Handles datetime objects and nested structures.
    """
    if obj is None:
        return None
        
    try:
        if hasattr(obj, "dict"):
            # If it's a Pydantic model
            data = obj.dict()
        elif hasattr(obj, "model_dump"):
            # For Pydantic v2
            data = obj.model_dump()
        elif isinstance(obj, dict):
            # Already a dict
            data = obj.copy()  # Make a copy to avoid modifying the original
        elif hasattr(obj, "__dict__"):
            # Has a __dict__ attribute
            data = {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
        else:
            # Try to convert to dict, but be careful
            try:
                data = safe_dict_conversion(obj)
                if not data and hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes)):
                    # If it's an empty dict but obj is iterable, it might be a list-like object
                    return [to_serializable_dict(item) if hasattr(item, "__iter__") and not isinstance(item, (str, bytes))
                           else item for item in obj]
            except (TypeError, ValueError):
                # If we can't convert to dict, return the object as is
                # or a string representation if it has __str__
                return str(obj) if hasattr(obj, "__str__") else repr(obj)
    except Exception as e:
        # If any exception occurs during conversion, return a safe value
        return f"Unconvertible object: {str(obj)[:100]}... (Error: {str(e)})"
    
    # Process all values recursively
    result = {}
    for key, value in data.items():
        if isinstance(value, (datetime, date)):
            result[key] = value.isoformat()
        elif isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, dict):
            result[key] = to_serializable_dict(value)
        elif isinstance(value, (list, tuple, set)):
            result[key] = [
                to_serializable_dict(item) if isinstance(item, (dict, object)) and not isinstance(item, (str, int, float, bool, type(None))) 
                else (str(item) if isinstance(item, ObjectId) else item) 
                for item in value
            ]
        else:
            # For other types, keep as is (basic types will serialize fine)
            result[key] = value
    
    return result 