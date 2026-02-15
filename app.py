"""
Voice Agent - Twilio Native Architecture

Uses:
- Twilio <Gather> for Speech-to-Text
- OpenAI Assistants API for conversation logic (with Zapier MCP)
- Twilio <Say>/<Play> for Text-to-Speech

NO MediaStream, NO OpenAI Realtime API
"""

from quart import Quart, request
from twilio.twiml.voice_response import VoiceResponse, Gather
import os
from dotenv import load_dotenv
import asyncio

from workflow_client import WorkflowClient

# Load environment
load_dotenv()

# Initialize Quart
app = Quart(__name__)

# Initialize workflow client (Assistants API + Zapier MCP)
workflow_client = WorkflowClient()

# Track active calls
active_calls = {}

print("=" * 70)
print("VOICE AGENT SYSTEM STARTED - TWILIO NATIVE")
print("=" * 70)
print("Using: Twilio STT + OpenAI Assistants + Zapier MCP")
print("=" * 70)
print("Using OpenAI Agents SDK + CRM MCP Server")




@app.route('/voice', methods=['POST'])
async def voice_webhook():
    """
    Initial call webhook from Twilio
    Returns TwiML with Gather for speech input
    """
    try:
        form = await request.form
        call_sid = form.get('CallSid')
        from_number = form.get('From')

        print(f"\n{'='*60}")
        print(f"[{call_sid}] NEW CALL from {from_number}")
        print(f"{'='*60}\n")

        # Initialize call state
        active_calls[call_sid] = {
            'from': from_number,
            'turn': 0
        }

        # Create workflow thread for this call
        await workflow_client.create_thread(call_sid)

        # Build TwiML response with speech gathering
        response = VoiceResponse()
        
        gather = Gather(
            input='speech',
            action='/process-speech',
            method='POST',
            timeout=10,
            speech_timeout=1,  # Pause after customer stops speaking
            language='en-US',
            enhanced=True,
            speech_model='phone_call'
        )
        
        # Initial greeting
        gather.say(
            "Elite Auto Service. How can I help you today?",
            voice='Google.en-US-Neural2-F',  # High-quality Google neural voice
            language='en-US'
        )
        
        response.append(gather)
        
        # Fallback if no speech detected
        response.say(
            "I didn't receive any input. Please call back when you're ready.",
            voice='Google.en-US-Neural2-F'
        )
        response.hangup()

        print(f"[{call_sid}] Sent greeting, waiting for customer speech...")
        
        return str(response), 200, {'Content-Type': 'text/xml'}
        
    except Exception as e:
        print(f"Error in /voice endpoint: {e}")
        import traceback
        traceback.print_exc()
        
        # Error fallback
        error_response = VoiceResponse()
        error_response.say(
            "Sorry, there was an error. Please try again later.",
            voice='Google.en-US-Neural2-F'
        )
        error_response.hangup()
        
        return str(error_response), 500, {'Content-Type': 'text/xml'}


@app.route('/process-speech', methods=['POST'])
async def process_speech():
    """
    Process customer speech using Assistants API
    Returns TwiML with agent response
    """
    try:
        form = await request.form
        call_sid = form.get('CallSid')
        customer_speech = form.get('SpeechResult', '').strip()
        confidence = float(form.get('Confidence', 0.0))
        
        print(f"\n[{call_sid}] Customer: '{customer_speech}' (confidence: {confidence:.2f})")

        # Validate call exists
        if call_sid not in active_calls:
            print(f"[{call_sid}] Warning: Call not in active calls, creating entry")
            active_calls[call_sid] = {'turn': 0}
            await workflow_client.create_thread(call_sid)

        # Handle low confidence
        if confidence < 0.4 or not customer_speech:
            print(f"[{call_sid}] Low confidence, asking for repeat")
            
            response = VoiceResponse()
            gather = Gather(
                input='speech',
                action='/process-speech',
                method='POST',
                timeout=10,
                speech_timeout=1
            )
            gather.say(
                "Sorry, I didn't catch that. Could you repeat?",
                voice='Google.en-US-Neural2-F'
            )
            response.append(gather)
            return str(response), 200, {'Content-Type': 'text/xml'}

        # Increment turn
        active_calls[call_sid]['turn'] += 1
        turn = active_calls[call_sid]['turn']
        
        print(f"[{call_sid}] Turn {turn}: Processing with Assistants API...")

        # Send to Assistants API (which will use Zapier MCP tools if needed)
        agent_response = await workflow_client.send_message(call_sid, customer_speech)
        
        print(f"[{call_sid}] Agent: '{agent_response}'")

        # Check for conversation end signals
        if _should_end_call(customer_speech, agent_response):
            print(f"[{call_sid}] Ending conversation")
            
            response = VoiceResponse()
            response.say(agent_response, voice='Google.en-US-Neural2-F')
            response.hangup()
            
            # Cleanup
            if call_sid in active_calls:
                del active_calls[call_sid]
            workflow_client.cleanup(call_sid)
            
            return str(response), 200, {'Content-Type': 'text/xml'}

        # Continue conversation
        response = VoiceResponse()
        
        gather = Gather(
            input='speech',
            action='/process-speech',
            method='POST',
            timeout=10,
            speech_timeout=1,
            language='en-US',
            enhanced=True,
            speech_model='phone_call'
        )
        
        # Agent speaks response
        gather.say(agent_response, voice='Google.en-US-Neural2-F', language='en-US')
        
        response.append(gather)
        
        # Fallback if customer doesn't respond
        response.say(
            "Are you still there? Call back if you need assistance.",
            voice='Google.en-US-Neural2-F'
        )
        response.hangup()

        return str(response), 200, {'Content-Type': 'text/xml'}
        
    except Exception as e:
        print(f"\n[{call_sid}] Error processing speech: {e}")
        import traceback
        traceback.print_exc()
        
        # Friendly fallback
        response = VoiceResponse()
        response.say(
            "I'm having trouble processing that. Let me connect you with someone who can help.",
            voice='Google.en-US-Neural2-F'
        )
        
        # Optional: Add transfer to human agent
        # response.dial(os.getenv('AGENT_TRANSFER_NUMBER', '+1234567890'))
        
        response.hangup()
        return str(response), 500, {'Content-Type': 'text/xml'}


@app.route('/call-status', methods=['POST'])
async def call_status():
    """
    Handle call status callbacks from Twilio
    """
    form = await request.form
    call_sid = form.get('CallSid')
    call_status = form.get('CallStatus')
    
    print(f"[{call_sid}] Call status: {call_status}")
    
    # Cleanup on call end
    if call_status in ['completed', 'failed', 'busy', 'no-answer']:
        if call_sid in active_calls:
            del active_calls[call_sid]
        workflow_client.cleanup(call_sid)
        print(f"[{call_sid}] Call ended, cleaned up")
    
    return 'OK', 200


@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return {
        "status": "healthy",
        "architecture": "twilio_native",
        "crm_mcp_connected": workflow_client._connected,
        "active_calls": len(active_calls)
    }


def _should_end_call(customer_speech: str, agent_response: str) -> bool:
    """
    Determine if conversation should end
    """
    customer_lower = customer_speech.lower()
    agent_lower = agent_response.lower()
    
    # Customer wants to end
    end_phrases = [
        'not interested', 'no thank', 'goodbye', 'bye',
        'stop calling', 'remove me', 'hang up'
    ]
    
    if any(phrase in customer_lower for phrase in end_phrases):
        return True
    
    # Agent ending conversation
    if any(phrase in agent_lower for phrase in ['goodbye', 'thank you for your time', 'have a great day']):
        return True
    
    return False


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f"Starting server on port {port}...")
    app.run(host='0.0.0.0', port=port)