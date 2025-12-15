"""Customer database operations."""

from typing import Optional, List
from models.customer import Customer, Vehicle, ServiceRecord
from utils.logger import setup_logger
from utils.validators import normalize_phone_number

logger = setup_logger(__name__)

# Mock database - replace with actual database queries
MOCK_CUSTOMERS = {
    '+11234567890': Customer(
        id='cust_001',
        name='John Doe',
        phone='+11234567890',
        email='john.doe@example.com',
        vehicle=Vehicle(
            make='Honda',
            model='Civic',
            year=2020,
            vin='1HGBH41JXMN109186',
            color='Blue',
            mileage=45000
        ),
        service_history=[
            ServiceRecord(
                id='svc_001',
                date='2024-10-15',
                service_type='oil_change',
                cost=59.99,
                mileage=42000,
                notes='Regular maintenance'
            ),
            ServiceRecord(
                id='svc_002',
                date='2024-08-10',
                service_type='tire_rotation',
                cost=39.99,
                mileage=40000
            )
        ],
        last_service_date='2024-10-15'
    )
}


async def get_customer_by_phone(phone: str) -> Optional[Customer]:
    """
    Look up customer by phone number.

    Args:
        phone: Customer phone number

    Returns:
        Customer object or None if not found
    """
    try:
        normalized_phone = normalize_phone_number(phone)
        logger.info(f"Looking up customer by phone: {normalized_phone}")

        customer = MOCK_CUSTOMERS.get(normalized_phone)

        if customer:
            logger.info(f"Customer found: {customer.id} - {customer.name}")
        else:
            logger.info(f"Customer not found for phone: {normalized_phone}")

        return customer

    except Exception as e:
        logger.error(f"Error looking up customer: {e}")
        return None


async def get_service_history(customer_id: str) -> List[ServiceRecord]:
    """
    Get customer's service history.

    Args:
        customer_id: Customer ID

    Returns:
        List of service records
    """
    try:
        logger.info(f"Getting service history for customer: {customer_id}")

        # Find customer
        for customer in MOCK_CUSTOMERS.values():
            if customer.id == customer_id:
                logger.info(f"Found {len(customer.service_history)} service records")
                return customer.service_history

        logger.info(f"No customer found with ID: {customer_id}")
        return []

    except Exception as e:
        logger.error(f"Error getting service history: {e}")
        return []


async def get_vehicle_info(customer_id: str) -> Optional[Vehicle]:
    """
    Get customer's vehicle details.

    Args:
        customer_id: Customer ID

    Returns:
        Vehicle object or None
    """
    try:
        logger.info(f"Getting vehicle info for customer: {customer_id}")

        # Find customer
        for customer in MOCK_CUSTOMERS.values():
            if customer.id == customer_id:
                return customer.vehicle

        logger.info(f"No customer found with ID: {customer_id}")
        return None

    except Exception as e:
        logger.error(f"Error getting vehicle info: {e}")
        return None


async def update_customer_info(customer_id: str, updates: dict) -> Optional[Customer]:
    """
    Update customer information.

    Args:
        customer_id: Customer ID
        updates: Dictionary of fields to update

    Returns:
        Updated customer object or None
    """
    try:
        logger.info(f"Updating customer info for: {customer_id}")

        # Find and update customer
        for phone, customer in MOCK_CUSTOMERS.items():
            if customer.id == customer_id:
                for key, value in updates.items():
                    if hasattr(customer, key):
                        setattr(customer, key, value)
                logger.info(f"Customer updated: {customer_id}")
                return customer

        logger.info(f"No customer found with ID: {customer_id}")
        return None

    except Exception as e:
        logger.error(f"Error updating customer info: {e}")
        return None
