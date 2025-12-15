"""Input validation utilities."""

import re
from datetime import datetime
from typing import Optional
from config.constants import SERVICE_TYPES


def validate_phone_number(phone: str) -> bool:
    """
    Validate phone number format.

    Args:
        phone: Phone number string

    Returns:
        True if valid, False otherwise
    """
    if not phone:
        return False

    # Remove common formatting characters
    cleaned = re.sub(r'[\s\-\(\)\.]+', '', phone)

    # Check for valid E.164 format or 10-digit US number
    pattern = r'^\+?1?\d{10,15}$'
    return bool(re.match(pattern, cleaned))


def normalize_phone_number(phone: str) -> str:
    """
    Normalize phone number to E.164 format.

    Args:
        phone: Phone number string

    Returns:
        Normalized phone number
    """
    cleaned = re.sub(r'[\s\-\(\)\.]+', '', phone)

    # Add +1 for US numbers if not present
    if not cleaned.startswith('+'):
        if not cleaned.startswith('1'):
            cleaned = '1' + cleaned
        cleaned = '+' + cleaned

    return cleaned


def validate_service_type(service_type: str) -> bool:
    """
    Validate service type.

    Args:
        service_type: Service type string

    Returns:
        True if valid, False otherwise
    """
    return service_type.lower() in SERVICE_TYPES


def validate_datetime(dt_str: str) -> Optional[datetime]:
    """
    Validate and parse datetime string.

    Args:
        dt_str: Datetime string (ISO format)

    Returns:
        Parsed datetime object or None if invalid
    """
    try:
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None


def validate_date(date_str: str) -> bool:
    """
    Validate date string.

    Args:
        date_str: Date string (YYYY-MM-DD format)

    Returns:
        True if valid, False otherwise
    """
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def sanitize_input(text: str, max_length: int = 1000) -> str:
    """
    Sanitize customer input.

    Args:
        text: Input text
        max_length: Maximum allowed length

    Returns:
        Sanitized text
    """
    if not text:
        return ""

    # Truncate to max length
    sanitized = text[:max_length]

    # Remove potentially harmful characters
    sanitized = re.sub(r'[<>]', '', sanitized)

    return sanitized.strip()
