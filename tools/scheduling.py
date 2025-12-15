"""Appointment scheduling operations."""

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from models.appointment import Appointment, AppointmentSlot
from config.constants import SERVICE_DURATIONS, BUSINESS_HOURS, SLOT_INTERVAL_MINUTES, APPOINTMENT_STATUS_SCHEDULED
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Mock database for appointments
MOCK_APPOINTMENTS: Dict[str, Appointment] = {}


async def check_availability(
    service_type: str,
    preferred_date: str,
    preferred_time: Optional[str] = None
) -> Dict:
    """
    Check available appointment slots.

    Args:
        service_type: Type of service
        preferred_date: Preferred date (YYYY-MM-DD)
        preferred_time: Optional preferred time (HH:MM)

    Returns:
        Dictionary with available slots
    """
    try:
        logger.info(f"Checking availability for {service_type} on {preferred_date}")

        # Parse date
        date_obj = datetime.strptime(preferred_date, '%Y-%m-%d')
        day_name = date_obj.strftime('%A').lower()

        # Check if business is open
        hours = BUSINESS_HOURS.get(day_name)
        if not hours or hours[0] is None:
            logger.info(f"Business closed on {day_name}")
            return {
                'available': False,
                'slots': [],
                'message': f'We are closed on {day_name.capitalize()}s'
            }

        # Get service duration
        duration = SERVICE_DURATIONS.get(service_type, 60)

        # Generate available slots
        slots = []
        open_time, close_time = hours
        current_time = datetime.strptime(open_time, '%H:%M')
        end_time = datetime.strptime(close_time, '%H:%M')

        while current_time < end_time:
            time_str = current_time.strftime('%H:%M')

            # Check if slot is already booked
            is_booked = any(
                apt.datetime.date() == date_obj.date() and
                apt.datetime.strftime('%H:%M') == time_str and
                apt.status in ['scheduled', 'confirmed']
                for apt in MOCK_APPOINTMENTS.values()
            )

            if not is_booked:
                slots.append(AppointmentSlot(
                    date=preferred_date,
                    time=time_str,
                    duration_minutes=duration,
                    available=True
                ))

            current_time += timedelta(minutes=SLOT_INTERVAL_MINUTES)

        logger.info(f"Found {len(slots)} available slots")

        return {
            'available': len(slots) > 0,
            'slots': [slot.to_dict() for slot in slots[:5]],  # Return first 5 slots
            'service_type': service_type,
            'duration_minutes': duration
        }

    except Exception as e:
        logger.error(f"Error checking availability: {e}")
        return {
            'available': False,
            'slots': [],
            'error': str(e)
        }


async def schedule_appointment(
    customer_id: str,
    customer_phone: str,
    datetime_str: str,
    service_type: str,
    notes: Optional[str] = None
) -> Dict:
    """
    Schedule a new appointment.

    Args:
        customer_id: Customer ID
        customer_phone: Customer phone
        datetime_str: Appointment datetime (ISO format)
        service_type: Type of service
        notes: Optional notes

    Returns:
        Dictionary with appointment details
    """
    try:
        logger.info(f"Scheduling {service_type} for customer {customer_id}")

        # Parse datetime
        apt_datetime = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))

        # Get service duration
        duration = SERVICE_DURATIONS.get(service_type, 60)

        # Create appointment
        appointment_id = f"apt_{uuid.uuid4().hex[:8]}"
        appointment = Appointment(
            id=appointment_id,
            customer_id=customer_id,
            datetime=apt_datetime,
            service_type=service_type,
            duration_minutes=duration,
            status=APPOINTMENT_STATUS_SCHEDULED,
            notes=notes,
            created_at=datetime.now()
        )

        # Save to mock database
        MOCK_APPOINTMENTS[appointment_id] = appointment

        logger.info(f"Appointment scheduled: {appointment_id}")

        # Format confirmation message
        formatted_date = apt_datetime.strftime('%A, %B %d')
        formatted_time = apt_datetime.strftime('%I:%M %p')

        return {
            'success': True,
            'appointment_id': appointment_id,
            'confirmation': f"Scheduled {service_type.replace('_', ' ')} for {formatted_date} at {formatted_time}",
            'datetime': apt_datetime.isoformat(),
            'service_type': service_type,
            'duration_minutes': duration
        }

    except Exception as e:
        logger.error(f"Error scheduling appointment: {e}")
        return {
            'success': False,
            'error': str(e)
        }


async def cancel_appointment(
    appointment_id: str,
    reason: Optional[str] = None
) -> Dict:
    """
    Cancel an appointment.

    Args:
        appointment_id: Appointment ID
        reason: Optional cancellation reason

    Returns:
        Dictionary with cancellation result
    """
    try:
        logger.info(f"Cancelling appointment: {appointment_id}")

        appointment = MOCK_APPOINTMENTS.get(appointment_id)

        if not appointment:
            logger.warning(f"Appointment not found: {appointment_id}")
            return {
                'success': False,
                'error': 'Appointment not found'
            }

        # Update status
        appointment.status = 'cancelled'
        if reason:
            appointment.notes = f"{appointment.notes or ''}\nCancellation reason: {reason}".strip()

        logger.info(f"Appointment cancelled: {appointment_id}")

        return {
            'success': True,
            'appointment_id': appointment_id,
            'message': 'Appointment cancelled successfully'
        }

    except Exception as e:
        logger.error(f"Error cancelling appointment: {e}")
        return {
            'success': False,
            'error': str(e)
        }


async def get_upcoming_appointments(customer_id: str) -> List[Dict]:
    """
    Get customer's upcoming appointments.

    Args:
        customer_id: Customer ID

    Returns:
        List of upcoming appointments
    """
    try:
        logger.info(f"Getting upcoming appointments for customer: {customer_id}")

        now = datetime.now()
        upcoming = [
            apt.to_dict()
            for apt in MOCK_APPOINTMENTS.values()
            if apt.customer_id == customer_id and
            apt.datetime > now and
            apt.status in ['scheduled', 'confirmed']
        ]

        # Sort by datetime
        upcoming.sort(key=lambda x: x['datetime'])

        logger.info(f"Found {len(upcoming)} upcoming appointments")
        return upcoming

    except Exception as e:
        logger.error(f"Error getting upcoming appointments: {e}")
        return []
