"""
Utility Functions
Common helper functions used across the application
"""

from datetime import datetime
from typing import Optional, Union


def parse_datetime(value: Union[str, datetime, None]) -> Optional[datetime]:
    """
    Parse datetime from various formats
    
    Handles:
    - None -> None
    - datetime object -> return as-is
    - ISO format string -> parse to datetime
    - Invalid string -> None
    
    Args:
        value: String, datetime, or None
        
    Returns:
        datetime object or None
        
    Examples:
        >>> parse_datetime(None)
        None
        >>> parse_datetime(datetime(2025, 1, 1))
        datetime(2025, 1, 1, 0, 0)
        >>> parse_datetime("2025-01-01T10:30:00")
        datetime(2025, 1, 1, 10, 30)
        >>> parse_datetime("invalid")
        None
    """
    if value is None:
        return None
    
    if isinstance(value, datetime):
        return value
    
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except (ValueError, AttributeError):
            return None
    
    return None


def format_datetime(dt: Optional[datetime]) -> Optional[str]:
    """
    Format datetime to ISO string
    
    Args:
        dt: datetime object or None
        
    Returns:
        ISO format string or None
        
    Examples:
        >>> format_datetime(None)
        None
        >>> format_datetime(datetime(2025, 1, 1, 10, 30))
        '2025-01-01T10:30:00'
    """
    if dt is None:
        return None
    
    if isinstance(dt, datetime):
        return dt.isoformat()
    
    return None
