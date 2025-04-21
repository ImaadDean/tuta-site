from datetime import datetime, timezone, timedelta

def get_eat_time():
    """
    Get the current time in East Africa Time (EAT) timezone.
    EAT is UTC+3
    """
    # Create a UTC time
    utc_now = datetime.now(timezone.utc)
    
    # EAT is UTC+3
    eat_offset = timezone(timedelta(hours=3))
    
    # Convert to EAT
    eat_time = utc_now.astimezone(eat_offset)
    
    return eat_time 