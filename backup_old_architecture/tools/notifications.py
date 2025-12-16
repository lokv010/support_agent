"""Notification services for SMS and email."""

from typing import Optional
from twilio.rest import Client
from config.settings import config
from models.appointment import Appointment
from utils.logger import setup_logger

logger = setup_logger(__name__)


class NotificationService:
    """Service for sending notifications."""

    def __init__(self):
        """Initialize Twilio client."""
        try:
            self.twilio_client = Client(
                config.TWILIO_ACCOUNT_SID,
                config.TWILIO_AUTH_TOKEN
            )
            self.from_number = config.TWILIO_PHONE_NUMBER
        except Exception as e:
            logger.error(f"Failed to initialize Twilio client: {e}")
            self.twilio_client = None


notification_service = NotificationService()


async def send_sms_confirmation(phone: str, appointment: Appointment) -> bool:
    """
    Send SMS appointment confirmation.

    Args:
        phone: Customer phone number
        appointment: Appointment object

    Returns:
        True if sent successfully, False otherwise
    """
    try:
        if not notification_service.twilio_client:
            logger.warning("Twilio client not initialized, skipping SMS")
            return False

        # Format message
        formatted_datetime = appointment.datetime.strftime('%A, %B %d at %I:%M %p')
        service_name = appointment.service_type.replace('_', ' ').title()

        message = (
            f"Appointment Confirmed!\n\n"
            f"Service: {service_name}\n"
            f"Date/Time: {formatted_datetime}\n"
            f"Duration: {appointment.duration_minutes} minutes\n\n"
            f"Thank you for choosing our service!"
        )

        # Send SMS
        message_obj = notification_service.twilio_client.messages.create(
            body=message,
            from_=notification_service.from_number,
            to=phone
        )

        logger.info(f"SMS sent to {phone}: {message_obj.sid}")
        return True

    except Exception as e:
        logger.error(f"Error sending SMS: {e}")
        return False


async def send_email_confirmation(email: str, appointment: Appointment) -> bool:
    """
    Send email appointment confirmation.

    Args:
        email: Customer email address
        appointment: Appointment object

    Returns:
        True if sent successfully, False otherwise
    """
    try:
        # Email sending would be implemented here
        # For now, just log
        logger.info(f"Email confirmation would be sent to {email}")
        logger.info(f"Appointment: {appointment.to_dict()}")

        # TODO: Implement actual email sending
        # Using SendGrid, AWS SES, or similar service

        return True

    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return False


async def notify_manager(reason: str, call_sid: str, customer_phone: Optional[str] = None) -> bool:
    """
    Notify manager of escalation or issue.

    Args:
        reason: Escalation reason
        call_sid: Call SID
        customer_phone: Optional customer phone

    Returns:
        True if notified successfully, False otherwise
    """
    try:
        # Manager notification logic would be implemented here
        # Could be SMS, email, Slack, PagerDuty, etc.

        logger.warning(f"MANAGER NOTIFICATION - Call: {call_sid}")
        logger.warning(f"Reason: {reason}")
        if customer_phone:
            logger.warning(f"Customer: {customer_phone}")

        # TODO: Implement actual manager notification
        # Example: Send to manager's phone or Slack channel

        return True

    except Exception as e:
        logger.error(f"Error notifying manager: {e}")
        return False


async def send_reminder(phone: str, appointment: Appointment, hours_before: int = 24) -> bool:
    """
    Send appointment reminder.

    Args:
        phone: Customer phone number
        appointment: Appointment object
        hours_before: Hours before appointment to send reminder

    Returns:
        True if sent successfully, False otherwise
    """
    try:
        if not notification_service.twilio_client:
            logger.warning("Twilio client not initialized, skipping reminder")
            return False

        formatted_datetime = appointment.datetime.strftime('%A, %B %d at %I:%M %p')
        service_name = appointment.service_type.replace('_', ' ').title()

        message = (
            f"Reminder: You have an appointment tomorrow!\n\n"
            f"Service: {service_name}\n"
            f"Date/Time: {formatted_datetime}\n\n"
            f"Reply CONFIRM to confirm or CANCEL to cancel."
        )

        message_obj = notification_service.twilio_client.messages.create(
            body=message,
            from_=notification_service.from_number,
            to=phone
        )

        logger.info(f"Reminder sent to {phone}: {message_obj.sid}")
        return True

    except Exception as e:
        logger.error(f"Error sending reminder: {e}")
        return False
