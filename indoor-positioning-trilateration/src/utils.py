import datetime
import logging

def convert_string_to_datetime(timestamp_str):
    """
    Convert a timestamp string to a datetime object.
    
    Handles multiple timestamp formats:
    - "YYYY-MM-DD HH:MM:SS"
    - "YYYY-MM-DDTHH:MM:SS.ssssss" (ISO format)
    - "YYYY-MM-DDTHH:MM:SS.ssssssZ" (ISO8601 format with Z)
    
    Parameters:
    timestamp_str (str): The timestamp string to convert
    
    Returns:
    datetime: The converted datetime object
    """
    try:
        # Handle ISO8601 strings ending with 'Z'
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str[:-1] + '+00:00'
        # Try ISO format first (with T separator)
        if 'T' in timestamp_str:
            # Handle ISO format with microseconds
            return datetime.datetime.fromisoformat(timestamp_str)
        else:
            # Handle standard format "YYYY-MM-DD HH:MM:SS"
            return datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    except Exception as e:
        logging.warning(f"Failed to parse timestamp '{timestamp_str}': {str(e)}")
        # Return current time as fallback
        return datetime.datetime.now()