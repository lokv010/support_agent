"""Tool API endpoints called by Agent Workflow."""

from flask import Blueprint, request, jsonify
import asyncio
from tools.customer import get_customer_by_phone, get_service_history, get_vehicle_info
from tools.scheduling import check_availability, schedule_appointment, cancel_appointment, get_upcoming_appointments
from tools.notifications import send_sms_confirmation, send_email_confirmation
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Create blueprint for tool endpoints
tools_bp = Blueprint('tools', __name__, url_prefix='/tools')


def async_route(f):
    """Decorator to run async functions in Flask routes."""
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    wrapper.__name__ = f.__name__
    return wrapper


@tools_bp.route('/get-customer', methods=['POST'])
@async_route
async def get_customer():
    """
    Get customer by phone number.

    Request: {"phone": "+1234567890"}
    Response: {"found": true, "customer_id": "...", "name": "...", "vehicle": {...}, ...}
    """
    try:
        data = request.get_json()
        phone = data.get('phone')

        if not phone:
            return jsonify({'error': 'Phone number required'}), 400

        logger.info(f"Tool called: get-customer for {phone}")

        customer = await get_customer_by_phone(phone)

        if customer:
            return jsonify({
                'found': True,
                'customer_id': customer.id,
                'name': customer.name,
                'phone': customer.phone,
                'email': customer.email,
                'vehicle': customer.vehicle.to_dict() if customer.vehicle else None,
                'last_service_date': customer.last_service_date
            })
        else:
            return jsonify({
                'found': False,
                'message': 'Customer not found'
            })

    except Exception as e:
        logger.error(f"Error in get-customer endpoint: {e}")
        return jsonify({'error': str(e)}), 500


@tools_bp.route('/get-history', methods=['POST'])
@async_route
async def get_history():
    """
    Get customer service history.

    Request: {"customer_id": "cust_001"}
    Response: {"history": [{"date": "...", "service_type": "...", ...}]}
    """
    try:
        data = request.get_json()
        customer_id = data.get('customer_id')

        if not customer_id:
            return jsonify({'error': 'Customer ID required'}), 400

        logger.info(f"Tool called: get-history for {customer_id}")

        history = await get_service_history(customer_id)

        return jsonify({
            'history': [record.to_dict() for record in history]
        })

    except Exception as e:
        logger.error(f"Error in get-history endpoint: {e}")
        return jsonify({'error': str(e)}), 500


@tools_bp.route('/check-availability', methods=['POST'])
@async_route
async def check_availability_endpoint():
    """
    Check appointment availability.

    Request: {"service_type": "oil_change", "preferred_date": "2024-11-26"}
    Response: {"available": true, "slots": [...]}
    """
    try:
        data = request.get_json()
        service_type = data.get('service_type')
        preferred_date = data.get('preferred_date')
        preferred_time = data.get('preferred_time')

        if not service_type or not preferred_date:
            return jsonify({'error': 'Service type and preferred date required'}), 400

        logger.info(f"Tool called: check-availability for {service_type} on {preferred_date}")

        result = await check_availability(service_type, preferred_date, preferred_time)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in check-availability endpoint: {e}")
        return jsonify({'error': str(e)}), 500


@tools_bp.route('/schedule-appointment', methods=['POST'])
@async_route
async def schedule_appointment_endpoint():
    """
    Schedule an appointment.

    Request: {
        "customer_id": "cust_001",
        "customer_phone": "+1234567890",
        "datetime": "2024-11-26T09:00:00Z",
        "service_type": "oil_change",
        "notes": "Optional notes"
    }
    Response: {"success": true, "appointment_id": "...", "confirmation": "..."}
    """
    try:
        data = request.get_json()
        customer_id = data.get('customer_id')
        customer_phone = data.get('customer_phone')
        datetime_str = data.get('datetime')
        service_type = data.get('service_type')
        notes = data.get('notes')

        if not all([customer_id, customer_phone, datetime_str, service_type]):
            return jsonify({'error': 'Missing required fields'}), 400

        logger.info(f"Tool called: schedule-appointment for {customer_id}")

        result = await schedule_appointment(
            customer_id,
            customer_phone,
            datetime_str,
            service_type,
            notes
        )

        # Send confirmation SMS if successful
        if result.get('success'):
            from models.appointment import Appointment
            apt = Appointment.from_dict({
                'id': result['appointment_id'],
                'customer_id': customer_id,
                'datetime': result['datetime'],
                'service_type': service_type,
                'duration_minutes': result['duration_minutes']
            })
            await send_sms_confirmation(customer_phone, apt)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in schedule-appointment endpoint: {e}")
        return jsonify({'error': str(e)}), 500


@tools_bp.route('/cancel-appointment', methods=['POST'])
@async_route
async def cancel_appointment_endpoint():
    """
    Cancel an appointment.

    Request: {"appointment_id": "apt_12345", "reason": "Optional reason"}
    Response: {"success": true, "message": "..."}
    """
    try:
        data = request.get_json()
        appointment_id = data.get('appointment_id')
        reason = data.get('reason')

        if not appointment_id:
            return jsonify({'error': 'Appointment ID required'}), 400

        logger.info(f"Tool called: cancel-appointment for {appointment_id}")

        result = await cancel_appointment(appointment_id, reason)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in cancel-appointment endpoint: {e}")
        return jsonify({'error': str(e)}), 500


@tools_bp.route('/get-upcoming-appointments', methods=['POST'])
@async_route
async def get_upcoming_appointments_endpoint():
    """
    Get customer's upcoming appointments.

    Request: {"customer_id": "cust_001"}
    Response: {"appointments": [...]}
    """
    try:
        data = request.get_json()
        customer_id = data.get('customer_id')

        if not customer_id:
            return jsonify({'error': 'Customer ID required'}), 400

        logger.info(f"Tool called: get-upcoming-appointments for {customer_id}")

        appointments = await get_upcoming_appointments(customer_id)

        return jsonify({
            'appointments': appointments
        })

    except Exception as e:
        logger.error(f"Error in get-upcoming-appointments endpoint: {e}")
        return jsonify({'error': str(e)}), 500
