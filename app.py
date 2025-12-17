"""
Main Application

Async web app (Quart) that:
1. Receives Twilio calls
2. Opens WebSocket for media stream
3. Connects voice to workflow
"""

from flask import logging
from quart import Quart, request, websocket
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
import json
import os
from dotenv import load_dotenv

from voice_handler import VoiceHandler
from workflow_client import WorkflowClient

# Load environment
load_dotenv()

# Initialize Quart (async Flask)
app = Quart(__name__)

# Initialize handlers
workflow_client = WorkflowClient()
voice_handler = VoiceHandler(workflow_client)

print("=" * 70)
print("VOICE AGENT SYSTEM STARTED")
print("=" * 70)
print(f"Workflow ID: {os.getenv('AGENT_WORKFLOW_ID')}")
print("=" * 70)


@app.route('/voice', methods=['POST'])
async def voice_webhook():
    """
    Initial call webhook from Twilio
    """
    form = await request.form
    call_sid = form.get('CallSid')
    from_number = form.get('From')

    print(f"[{call_sid}] Incoming call from {from_number}")

    # Generate TwiML with Stream (no Say - greeting will come from OpenAI)
    response = VoiceResponse()

    connect = Connect()
    stream = Stream(url=f"wss://{request.host}/media-stream")
    connect.append(stream)
    response.append(connect)

    return str(response)


@app.websocket('/media-stream')
async def media_stream():
    """
    WebSocket for Twilio media stream
    """
    call_sid = None

    try:
        while True:
        # Get first message
            first_message = await websocket.receive()
            data = json.loads(first_message)

            if data.get('event') == 'start':
                call_sid = data['start']['callSid']
                print(f"[{call_sid}] Media stream started")
                break

                # Handle the call
        await voice_handler.handle_call(call_sid, websocket)

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
    app.run(host='localhost', port=port)
