"""
Main Application

Async web app (Quart) that:
1. Receives Twilio calls
2. Opens WebSocket for media stream
3. Connects voice to workflow
"""

from quart import Quart, request, websocket
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
import json
import os
from dotenv import load_dotenv

from voice_handler_backup import VoiceHandler
from workflow_client_backup import WorkflowClient

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
print("Using OpenAI Agents SDK")
print("=" * 70)


@app.route('/voice', methods=['POST'])
async def voice_webhook():
    """
    Initial call webhook from Twilio
    """
    try:
        form = await request.form
        call_sid = form.get('CallSid')
        from_number = form.get('From')

        print(f"[{call_sid}] Incoming call from {from_number}")

        # Generate TwiML with Stream (no Say - greeting will come from OpenAI)
        response = VoiceResponse()

        connect = Connect()
        host = request.headers.get('Host')
        ws_url = f"wss://{host}/media-stream"
        stream = Stream(url=ws_url)
        stream.parameter(name="call_sid", value=call_sid)
        stream.parameter(name="track", value='both_tracks')
        connect.append(stream)
        response.append(connect)
        twiml_str = str(response)
        print(f"[{call_sid}] Returning TwiML: {twiml_str[:200]}...")  # Print first 200 chars
            
        return twiml_str, 200, {'Content-Type': 'text/xml'}
    except Exception as e:
        print(f"Error in /voice endpoint: {e}")
        import traceback
        traceback.print_exc()
        
        # ✅ ADD: Return error TwiML
        error_response = VoiceResponse()
        error_response.say("Sorry, there was an error. Please try again later.", voice='Polly.Joanna')
        error_response.hangup()
        
        return str(error_response), 500, {'Content-Type': 'text/xml'}


@app.websocket('/media-stream')
async def media_stream():
    """
    WebSocket for Twilio media stream
    """
    call_sid = None
    stream_sid = None

    try:
        while True:
        # Get first message
            first_message = await websocket.receive()
            data = json.loads(first_message)

            if data.get('event') == 'start':
                call_sid = data['start']['callSid']
                stream_sid = data['start']['streamSid']
                print(f"[{call_sid}] Media stream started")
                break

                # Handle the call
        await voice_handler.handle_call(call_sid, stream_sid, websocket)

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
