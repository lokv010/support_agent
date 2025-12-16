# DEVELOPMENT INSTRUCTIONS - SIMPLIFIED
## Twilio + OpenAI Realtime + OpenAI Agent Workflow
### No Tool APIs, No Context Enrichment, No Overhead

---

## THE SIMPLE TRUTH

You have a **published Agent Workflow** that already has:
- ✅ All business logic
- ✅ All tools
- ✅ All data access
- ✅ All intelligence

**You just need to connect voice to it.**

---

## SIMPLE FLOW

```
Customer speaks
    ↓
OpenAI Realtime (STT - Speech to Text)
    ↓
Agent Workflow (OpenAI SDK - thinks, decides, acts)
    ↓
OpenAI Realtime (TTS - Text to Speech)
    ↓
Customer hears
```

**That's it!**

---

## PROJECT STRUCTURE (MINIMAL)

```
voice-agent/
├── app.py                  # Main app (Flask + WebSocket)
├── voice_handler.py        # OpenAI Realtime integration
├── workflow_client.py      # OpenAI SDK for Agent Workflow
├── utils.py               # Audio conversion
├── requirements.txt
├── .env.example
└── README.md
```

**Total files: 6**

---

## STEP 1: SETUP

### Create requirements.txt

```
# Web Framework
flask==3.0.0
flask-sock==0.7.0

# OpenAI SDK
openai>=1.54.0

# Twilio
twilio==8.10.0

# Audio
audioop-lts

# Environment
python-dotenv==1.0.0
```

### Create .env.example

```bash
# Twilio
TWILIO_ACCOUNT_SID=ACxxxxx
TWILIO_AUTH_TOKEN=your_token
TWILIO_PHONE_NUMBER=+1234567890
WEBHOOK_URL=https://your-domain.com

# OpenAI
OPENAI_API_KEY=sk-xxxxx

# Agent Workflow
AGENT_WORKFLOW_ID=workflow_xxxxx  # Your published workflow ID

# Server
PORT=5000
```

---

## STEP 2: AUDIO UTILITIES

### utils.py

```python
"""Audio conversion utilities"""

import audioop
import base64

def mulaw_to_pcm16(mulaw_data: bytes) -> bytes:
    """Convert Twilio mulaw to OpenAI PCM16"""
    return audioop.ulaw2lin(mulaw_data, 2)

def pcm16_to_mulaw(pcm_data: bytes) -> bytes:
    """Convert OpenAI PCM16 to Twilio mulaw"""
    return audioop.lin2ulaw(pcm_data, 2)

def encode_base64(data: bytes) -> str:
    """Encode to base64 string"""
    return base64.b64encode(data).decode('utf-8')

def decode_base64(data: str) -> bytes:
    """Decode from base64 string"""
    return base64.b64decode(data)
```

---

## STEP 3: WORKFLOW CLIENT

### workflow_client.py

```python
"""
Agent Workflow Integration using OpenAI SDK

This is the BRAIN of the system.
Your published workflow has all the business logic.
"""

from openai import OpenAI
import os

class WorkflowClient:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.workflow_id = os.getenv('AGENT_WORKFLOW_ID')
        self.threads = {}  # call_sid → thread_id
    
    def create_thread(self, call_sid: str) -> str:
        """
        Create conversation thread for this call
        
        Args:
            call_sid: Twilio call SID
            
        Returns:
            thread_id
        """
        thread = self.client.beta.threads.create()
        self.threads[call_sid] = thread.id
        print(f"[{call_sid}] Created thread: {thread.id}")
        return thread.id
    
    def send_message(self, call_sid: str, text: str) -> str:
        """
        Send message to Agent Workflow, get response
        
        This is where ALL the magic happens:
        - Workflow understands intent
        - Workflow fetches any context it needs
        - Workflow executes any actions
        - Workflow returns final response
        
        Args:
            call_sid: Call SID
            text: Customer message (from STT)
            
        Returns:
            Agent response text (for TTS)
        """
        thread_id = self.threads.get(call_sid)
        
        if not thread_id:
            thread_id = self.create_thread(call_sid)
        
        print(f"[{call_sid}] → Workflow: {text}")
        
        # Add message to thread
        self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=text
        )
        
        # Run the workflow
        run = self.client.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=self.workflow_id
        )
        
        # Get response
        if run.status == 'completed':
            messages = self.client.beta.threads.messages.list(
                thread_id=thread_id
            )
            
            # Get the latest assistant message
            for message in messages.data:
                if message.role == "assistant":
                    response_text = message.content[0].text.value
                    print(f"[{call_sid}] ← Workflow: {response_text}")
                    return response_text
        
        # Fallback
        return "I'm having trouble right now. Let me transfer you to our team."
    
    def cleanup(self, call_sid: str):
        """Clean up thread"""
        if call_sid in self.threads:
            del self.threads[call_sid]
            print(f"[{call_sid}] Thread cleaned up")
```

**That's it! No tool execution, no context enrichment - the workflow handles everything.**

---

## STEP 4: VOICE HANDLER

### voice_handler.py

```python
"""
OpenAI Realtime Voice Handler

Handles:
- Audio streaming (Twilio ↔ OpenAI)
- STT (Speech to Text)
- TTS (Text to Speech)

Does NOT handle:
- Business logic (Workflow does this)
"""

import asyncio
import json
import websockets
import os
from utils import mulaw_to_pcm16, pcm16_to_mulaw, encode_base64, decode_base64

class VoiceHandler:
    def __init__(self, workflow_client):
        self.workflow_client = workflow_client
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.connections = {}  # call_sid → openai_ws
    
    async def connect(self, call_sid: str):
        """Connect to OpenAI Realtime API"""
        url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }
        
        ws = await websockets.connect(url, extra_headers=headers)
        self.connections[call_sid] = ws
        
        # Configure session (VOICE ONLY - no business logic!)
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": "You are a voice interface. Just listen and speak what you're told.",
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "silence_duration_ms": 500
                }
            }
        }))
        
        print(f"[{call_sid}] Connected to OpenAI Realtime")
    
    async def handle_call(self, call_sid: str, twilio_ws):
        """
        Handle complete call
        
        This manages the audio streams and connects to workflow
        """
        # Connect to OpenAI
        await self.connect(call_sid)
        openai_ws = self.connections[call_sid]
        
        # Create workflow thread
        self.workflow_client.create_thread(call_sid)
        
        try:
            # Run both audio streams concurrently
            await asyncio.gather(
                self._stream_customer_audio(call_sid, twilio_ws, openai_ws),
                self._stream_agent_audio(call_sid, twilio_ws, openai_ws)
            )
        except Exception as e:
            print(f"[{call_sid}] Error: {e}")
        finally:
            await self.cleanup(call_sid)
    
    async def _stream_customer_audio(self, call_sid: str, twilio_ws, openai_ws):
        """
        Stream customer audio: Twilio → OpenAI Realtime
        """
        async for message in twilio_ws:
            try:
                data = json.loads(message)
                
                if data.get('event') == 'media':
                    # Get audio from Twilio
                    mulaw_data = decode_base64(data['media']['payload'])
                    
                    # Convert to PCM16
                    pcm_data = mulaw_to_pcm16(mulaw_data)
                    
                    # Send to OpenAI
                    await openai_ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": encode_base64(pcm_data)
                    }))
                    
            except Exception as e:
                print(f"[{call_sid}] Customer audio error: {e}")
    
    async def _stream_agent_audio(self, call_sid: str, twilio_ws, openai_ws):
        """
        Stream agent audio: OpenAI Realtime → Twilio
        AND handle transcriptions → workflow
        """
        async for message in openai_ws:
            try:
                data = json.loads(message)
                event_type = data.get('type')
                
                # Customer finished speaking - transcription ready
                if event_type == 'conversation.item.input_audio_transcription.completed':
                    transcript = data.get('transcript', '').strip()
                    
                    if transcript:
                        print(f"[{call_sid}] Customer said: {transcript}")
                        
                        # Send to workflow, get response
                        response_text = self.workflow_client.send_message(
                            call_sid,
                            transcript
                        )
                        
                        # Tell OpenAI Realtime to speak the response
                        await openai_ws.send(json.dumps({
                            "type": "response.create",
                            "response": {
                                "modalities": ["audio"],
                                "instructions": f"Say this: {response_text}"
                            }
                        }))
                
                # Agent audio output
                elif event_type == 'response.audio.delta':
                    # Get audio from OpenAI
                    pcm_data = decode_base64(data.get('delta', ''))
                    
                    # Convert to mulaw
                    mulaw_data = pcm16_to_mulaw(pcm_data)
                    
                    # Send to Twilio
                    await twilio_ws.send(json.dumps({
                        "event": "media",
                        "media": {
                            "payload": encode_base64(mulaw_data)
                        }
                    }))
                    
            except Exception as e:
                print(f"[{call_sid}] Agent audio error: {e}")
    
    async def cleanup(self, call_sid: str):
        """Clean up connections"""
        if call_sid in self.connections:
            await self.connections[call_sid].close()
            del self.connections[call_sid]
        
        self.workflow_client.cleanup(call_sid)
        print(f"[{call_sid}] Call ended")
```

---

## STEP 5: MAIN APPLICATION

### app.py

```python
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
    app.run(host='0.0.0.0', port=port)
```

---

## STEP 6: README

### README.md

```markdown
# Voice Agent System

Simple voice AI system connecting:
- Twilio (phone calls)
- OpenAI Realtime (voice)
- OpenAI Agent Workflow (brain)

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. Run:
```bash
python app.py
```

4. Configure Twilio:
- Set webhook: `https://your-domain.com/voice`

## How It Works

```
Customer speaks
    ↓
OpenAI Realtime (STT)
    ↓
Agent Workflow (thinks & acts)
    ↓
OpenAI Realtime (TTS)
    ↓
Customer hears
```

Your Agent Workflow handles ALL business logic.
This code just connects voice to it.

## Files

- `app.py` - Flask app + WebSocket
- `voice_handler.py` - OpenAI Realtime integration
- `workflow_client.py` - Agent Workflow integration (OpenAI SDK)
- `utils.py` - Audio conversion

Total: ~300 lines of code
```

---

## THAT'S IT!

### What You Have

**3 main files:**
1. `app.py` (~50 lines) - Flask + WebSocket
2. `voice_handler.py` (~150 lines) - Voice streaming
3. `workflow_client.py` (~80 lines) - Workflow integration

**Total: ~300 lines**

### What You DON'T Have

- ❌ No tool API endpoints
- ❌ No context enrichment
- ❌ No manual tool execution
- ❌ No database code
- ❌ No complex orchestration

### Why?

**Because your published Agent Workflow already has all of that!**

---

## Flow Summary

```python
# Customer speaks: "I need an oil change"

# 1. OpenAI Realtime transcribes
transcript = "I need an oil change"

# 2. Send to Agent Workflow
response = workflow_client.send_message(call_sid, transcript)
# Workflow does EVERYTHING:
#   - Understands intent
#   - Looks up customer
#   - Checks availability
#   - Generates response

# 3. OpenAI Realtime speaks response
# Response: "We have Tuesday at 9 AM or Thursday at 2 PM"
```

**Simple!**

---

## Testing

```bash
# Run the app
python app.py

# Call your Twilio number
# Say: "I need an oil change"
# Agent should respond intelligently
```

---

## Deployment

1. Deploy to any Python hosting (Heroku, Railway, etc.)
2. Set environment variables
3. Configure Twilio webhook
4. Done!

---

## Key Principle

**Your code = Thin voice interface**
**Agent Workflow = Smart brain**

Keep it simple!