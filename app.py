"""Main application for Car Service Voice AI System."""

import asyncio
import json
import threading
from flask import Flask, request, Response
from flask_cors import CORS
from flask_sock import Sock
import websockets

from config.settings import config
from layers.voice_interface import VoiceInterfaceHandler
from layers.workflow_client import WorkflowClient
from layers.orchestrator import Orchestrator
from services.twilio_handler import TwilioHandler
from services.session_manager import session_manager
from tools.api import tools_bp
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Initialize Flask
app = Flask(__name__)
CORS(app)
sock = Sock(app)

# Initialize handlers
voice_handler = VoiceInterfaceHandler()
workflow_client = WorkflowClient()
orchestrator = Orchestrator(voice_handler, workflow_client)
twilio_handler = TwilioHandler()

# Set transcription callback
voice_handler.set_transcription_callback(orchestrator.handle_customer_message)

# Register tool endpoints blueprint
app.register_blueprint(tools_bp)


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return {
        'status': 'healthy',
        'active_sessions': session_manager.get_session_count()
    }


@app.route('/voice', methods=['POST'])
def voice_webhook():
    """
    Twilio voice webhook - initial call connection.

    Returns TwiML with media stream configuration.
    """
    try:
        call_sid = request.values.get('CallSid')
        from_number = request.values.get('From')

        logger.info(f"Incoming call: {call_sid} from {from_number}")

        # Generate TwiML with media stream
        twiml = twilio_handler.generate_initial_twiml()

        return Response(twiml, mimetype='text/xml')

    except Exception as e:
        logger.error(f"Error in voice webhook: {e}")
        twiml = twilio_handler.generate_hangup_twiml(
            "We're experiencing technical difficulties. Please call back later."
        )
        return Response(twiml, mimetype='text/xml')


@sock.route('/media-stream')
def media_stream_handler(ws):
    """
    WebSocket handler for Twilio media stream.

    This is the main entry point for bidirectional audio streaming.
    """
    call_sid = None
    stream_sid = None

    try:
        logger.info("WebSocket connection established")

        # Process messages
        while True:
            message = ws.receive()
            if message is None:
                break

            data = json.loads(message)
            event_type = data.get('event')

            if event_type == 'start':
                # Stream started
                start_data = data.get('start', {})
                call_sid = start_data.get('callSid')
                stream_sid = start_data.get('streamSid')
                customer_phone = start_data.get('customParameters', {}).get('From', '')

                logger.info(f"Stream started: {stream_sid} for call {call_sid}")

                # Initialize session
                asyncio.run(handle_stream_start(ws, call_sid, stream_sid, customer_phone))

            elif event_type == 'media':
                # Audio data - handled by voice interface
                pass

            elif event_type == 'stop':
                # Stream stopped
                logger.info(f"Stream stopped: {stream_sid}")
                if call_sid:
                    asyncio.run(orchestrator.end_call(call_sid))
                break

    except Exception as e:
        logger.error(f"Error in media stream handler: {e}")
        if call_sid:
            asyncio.run(orchestrator.end_call(call_sid))


async def handle_stream_start(ws, call_sid: str, stream_sid: str, customer_phone: str):
    """
    Handle stream start event.

    Args:
        ws: WebSocket connection
        call_sid: Call SID
        stream_sid: Stream SID
        customer_phone: Customer phone number
    """
    try:
        # Connect to OpenAI Realtime
        connected = await voice_handler.connect(call_sid)

        if not connected:
            logger.error(f"Failed to connect to OpenAI Realtime for {call_sid}")
            return

        # Start orchestrator session
        session = await orchestrator.start_call(call_sid, stream_sid, customer_phone)

        # Start media stream handling
        await voice_handler.handle_media_stream(ws, call_sid)

    except Exception as e:
        logger.error(f"Error handling stream start: {e}")


def print_startup_banner():
    """Print startup information."""
    print("=" * 70)
    print("STARTING CAR SERVICE VOICE AI SYSTEM")
    print("=" * 70)
    print(f"OpenAI Realtime Model: {config.OPENAI_REALTIME_MODEL}")
    print(f"OpenAI Voice: {config.OPENAI_VOICE}")
    print(f"Agent Workflow URL: {config.AGENT_WORKFLOW_URL}")
    print(f"Tools Base URL: {config.WEBHOOK_URL}/tools")
    print("=" * 70)
    print(f"Flask Server: http://{config.WEBSOCKET_HOST}:{config.FLASK_PORT}")
    print(f"WebSocket: wss://{config.WEBHOOK_URL.replace('https://', '').replace('http://', '')}/media-stream")
    print("=" * 70)
    print("\nTool Endpoints (for Agent Workflow):")
    print(f"  - POST {config.WEBHOOK_URL}/tools/get-customer")
    print(f"  - POST {config.WEBHOOK_URL}/tools/get-history")
    print(f"  - POST {config.WEBHOOK_URL}/tools/check-availability")
    print(f"  - POST {config.WEBHOOK_URL}/tools/schedule-appointment")
    print(f"  - POST {config.WEBHOOK_URL}/tools/cancel-appointment")
    print(f"  - POST {config.WEBHOOK_URL}/tools/get-upcoming-appointments")
    print("=" * 70)
    print("\nWaiting for calls...\n")


if __name__ == '__main__':
    # Validate configuration
    if not config.validate():
        print("ERROR: Configuration validation failed. Please check your .env file.")
        exit(1)

    # Print startup banner
    print_startup_banner()

    # Run Flask app
    app.run(
        host=config.WEBSOCKET_HOST,
        port=config.FLASK_PORT,
        debug=False
    )
