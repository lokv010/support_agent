"""Tests for tool functions."""

import pytest
from datetime import datetime
from tools.customer import get_customer_by_phone
from tools.scheduling import check_availability


@pytest.mark.asyncio
async def test_get_customer():
    """Test customer lookup."""
    # Test with existing customer
    customer = await get_customer_by_phone('+11234567890')
    assert customer is not None
    assert customer.name == 'John Doe'
    assert customer.vehicle is not None

    # Test with non-existing customer
    customer = await get_customer_by_phone('+19999999999')
    assert customer is None


@pytest.mark.asyncio
async def test_check_availability():
    """Test availability checking."""
    result = await check_availability(
        service_type='oil_change',
        preferred_date='2024-12-20'
    )

    assert 'available' in result
    assert 'slots' in result
    assert isinstance(result['slots'], list)


def test_service_duration():
    """Test service duration constants."""
    from config.constants import SERVICE_DURATIONS

    assert SERVICE_DURATIONS.get('oil_change') == 30
    assert SERVICE_DURATIONS.get('brake_service') == 90
