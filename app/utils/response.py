from fastapi.responses import JSONResponse
from typing import Dict, Any
import json
from datetime import datetime

class CustomJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle datetime objects and other non-serializable types"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def create_json_response(content: Dict[str, Any], status_code: int = 200) -> JSONResponse:
    """
    Create a JSONResponse with proper datetime serialization
    
    Args:
        content: Dictionary content to return in the response
        status_code: HTTP status code for the response
        
    Returns:
        JSONResponse with properly serialized content
    """
    json_content = json.dumps(content, cls=CustomJSONEncoder)
    return JSONResponse(content=json.loads(json_content), status_code=status_code)
