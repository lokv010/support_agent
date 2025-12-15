"""Twilio TwiML generation and handling."""

from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from config.settings import config
from utils.logger import setup_logger

logger = setup_logger(__name__)


class TwilioHandler:
    """Handler for Twilio operations."""

    def __init__(self):
        self.webhook_url = config.WEBHOOK_URL
        self.websocket_url = f"wss://{config.WEBHOOK_URL.replace('https://', '').replace('http://', '')}/media-stream"

    def generate_initial_twiml(self) -> str:
        """
        Generate TwiML for initial call connection.

        Returns:
            TwiML string with Stream connection
        """
        try:
            response = VoiceResponse()

            # Create Connect element with Stream
            connect = Connect()
            stream = Stream(url=self.websocket_url)
            connect.append(stream)
            response.append(connect)

            twiml_str = str(response)
            logger.info("Generated initial TwiML with Stream")
            return twiml_str

        except Exception as e:
            logger.error(f"Error generating TwiML: {e}")
            # Fallback TwiML
            response = VoiceResponse()
            response.say("We're experiencing technical difficulties. Please call back later.")
            response.hangup()
            return str(response)

    def generate_transfer_twiml(self, transfer_number: str) -> str:
        """
        Generate TwiML for call transfer to human agent.

        Args:
            transfer_number: Phone number to transfer to

        Returns:
            TwiML string for call transfer
        """
        try:
            response = VoiceResponse()
            response.say("Please hold while I transfer you to an agent.")
            response.dial(transfer_number)

            logger.info(f"Generated transfer TwiML to {transfer_number}")
            return str(response)

        except Exception as e:
            logger.error(f"Error generating transfer TwiML: {e}")
            # Fallback
            response = VoiceResponse()
            response.say("Unable to transfer at this time. Please call our main number.")
            response.hangup()
            return str(response)

    def generate_hangup_twiml(self, message: str = None) -> str:
        """
        Generate TwiML to end the call.

        Args:
            message: Optional message to say before hanging up

        Returns:
            TwiML string for hangup
        """
        try:
            response = VoiceResponse()

            if message:
                response.say(message)

            response.hangup()

            logger.info("Generated hangup TwiML")
            return str(response)

        except Exception as e:
            logger.error(f"Error generating hangup TwiML: {e}")
            response = VoiceResponse()
            response.hangup()
            return str(response)
