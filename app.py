"""
Main Application

Simple Flask app that:
1. Receives Twilio calls
2. Opens WebSocket for media stream
3. Connects voice to workflow
"""

from flask import Flask, request
from flask_sock import Sock
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
import json
import os
from dotenv import load_dotenv

from voice_handler import VoiceHandler
from workflow_client import WorkflowClient

# Load environment
load_dotenv()

# Initialize Flask
app = Flask(__name__)
sock = Sock(app)

# Initialize handlers
workflow_client = WorkflowClient()
voice_handler = VoiceHandler(workflow_client)

print("=" * 70)
print("VOICE AGENT SYSTEM STARTED")
print("=" * 70)
print(f"Workflow ID: {os.getenv('AGENT_WORKFLOW_ID')}")
print("=" * 70)


@app.route('/voice', methods=['POST'])
def voice_webhook():
    """
    Initial call webhook from Twilio
    """
    call_sid = request.form.get('CallSid')
    from_number = request.form.get('From')

    print(f"[{call_sid}] Incoming call from {from_number}")

    # Generate TwiML with Stream
    response = VoiceResponse()
    response.say("Hello! How can I help you today?")

    connect = Connect()
    stream = Stream(url=f"wss://{request.host}/media-stream")
    connect.append(stream)
    response.append(connect)

    return str(response)


@sock.route('/media-stream')
async def media_stream(ws):
    """
    WebSocket for Twilio media stream
    """
    call_sid = None

    try:
        # Get first message
        first_message = await ws.receive()
        data = json.loads(first_message)

        if data.get('event') == 'start':
            call_sid = data['start']['callSid']
            print(f"[{call_sid}] Media stream started")

            # Handle the call
            await voice_handler.handle_call(call_sid, ws)

    except Exception as e:
        if call_sid:
            print(f"[{call_sid}] WebSocket error: {e}")
        else:
            print(f"WebSocket error: {e}")


@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return {"status": "healthy"}


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f"Starting server on port {port}...")
    app.run(host='0.0.0.0', port=port)
