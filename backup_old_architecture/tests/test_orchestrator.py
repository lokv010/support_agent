"""Tests for orchestrator layer."""

import pytest
from utils.validators import validate_phone_number, normalize_phone_number, validate_service_type


def test_phone_validation():
    """Test phone number validation."""
    assert validate_phone_number('+11234567890') == True
    assert validate_phone_number('1234567890') == True
    assert validate_phone_number('123') == False
    assert validate_phone_number('') == False


def test_phone_normalization():
    """Test phone number normalization."""
    assert normalize_phone_number('1234567890') == '+11234567890'
    assert normalize_phone_number('(123) 456-7890') == '+11234567890'
    assert normalize_phone_number('+1234567890') == '+1234567890'


def test_service_type_validation():
    """Test service type validation."""
    assert validate_service_type('oil_change') == True
    assert validate_service_type('tire_rotation') == True
    assert validate_service_type('invalid_service') == False
