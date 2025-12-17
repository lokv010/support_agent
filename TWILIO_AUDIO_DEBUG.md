# Twilio Audio Troubleshooting Guide

This guide helps debug the "unable to hear any voice from system" issue.

## Quick Diagnostic Checklist

Run through this checklist to identify the issue:

### 1. Server Running?
```bash
# Check if server is running
curl http://localhost:5000/health
# Expected: {"status": "healthy"}
```

### 2. WebSocket Connection Established?

Check server logs for:
```
[CallSid] Media stream started
[CallSid] Connected to OpenAI Realtime
```

If you don't see these, the WebSocket isn't connecting properly.

### 3. Audio Flowing IN (Customer → System)?

Check logs for:
```
[CallSid] Customer said: [transcription]
```

If you see this, customer audio IS reaching OpenAI (STT working).

### 4. Assistant Responding?

Check logs for:
```
[CallSid] → Assistant: [customer message]
[CallSid] Run status: in_progress
[CallSid] Run status: completed
[CallSid] ← Assistant: [assistant response]
```

If you see this, the Assistant IS generating responses.

### 5. Audio Flowing OUT (System → Customer)?

This is where the issue usually is. Look for:
```python
# In voice_handler.py, _stream_agent_audio method
# Should be sending audio chunks to Twilio
```

## Common Issues & Fixes

### Issue 1: No WebSocket Connection

**Symptoms:**
- No `Media stream started` in logs
- Call connects but immediately disconnects

**Causes:**
- Twilio webhook URL incorrect
- Server not accessible from internet
- HTTPS required but HTTP provided

**Fix:**
```bash
# 1. Verify webhook URL is correct
echo $WEBHOOK_URL

# 2. Test server is accessible
curl https://your-domain.com/voice

# 3. Use ngrok for local testing
ngrok http 5000
# Then update Twilio webhook to ngrok URL
```

### Issue 2: OpenAI Realtime Not Connecting

**Symptoms:**
- `Media stream started` appears
- No `Connected to OpenAI Realtime` in logs
- Error about WebSocket connection

**Causes:**
- Invalid OpenAI API key
- No Realtime API access
- Network/firewall blocking WebSocket

**Fix:**
```python
# Test OpenAI connection
import asyncio
import websockets
import os
import json

async def test_openai_ws():
    api_key = os.getenv('OPENAI_API_KEY')
    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1"
    }

    try:
        async with websockets.connect(url, extra_headers=headers) as ws:
            print("✓ Connected to OpenAI Realtime!")
            # Send session.update
            await ws.send(json.dumps({
                "type": "session.update",
                "session": {"modalities": ["text", "audio"]}
            }))
            # Wait for response
            response = await ws.recv()
            print(f"✓ Response: {response}")
    except Exception as e:
        print(f"✗ Error: {e}")

asyncio.run(test_openai_ws())
```

### Issue 3: Audio Not Playing (Most Common)

**Symptoms:**
- Everything connects successfully
- Transcriptions appear in logs
- Assistant responses appear in logs
- But customer hears nothing

**Causes:**
1. **Audio format mismatch**: Twilio expects mulaw, OpenAI sends PCM16
2. **Missing audio conversion**: `pcm16_to_mulaw` not working
3. **Audio not being sent to Twilio WebSocket**
4. **OpenAI not generating audio** (only text)

**Debug Steps:**

#### Step 1: Verify OpenAI is Generating Audio
```python
# Add debug logging to voice_handler.py around line 177

elif event_type == 'response.audio.delta':
    print(f"[{call_sid}] 🔊 Received audio delta: {len(data.get('delta', ''))} bytes")
    # ... rest of code
```

If you DON'T see `🔊 Received audio delta`, OpenAI isn't generating audio.

**Fix for OpenAI not generating audio:**

Check `voice_handler.py` line 168-174:
```python
# Make sure you're asking for audio output
await openai_ws.send(json.dumps({
    "type": "response.create",
    "response": {
        "modalities": ["audio"],  # Must be "audio", not "text"
        "instructions": f"Say this: {response_text}"
    }
}))
```

#### Step 2: Verify Audio Conversion
```python
# Add debug logging to voice_handler.py around line 179

# Get audio from OpenAI
pcm_data = decode_base64(data.get('delta', ''))
print(f"[{call_sid}] 📦 PCM data: {len(pcm_data)} bytes")

# Convert to mulaw
mulaw_data = pcm16_to_mulaw(pcm_data)
print(f"[{call_sid}] 📦 mulaw data: {len(mulaw_data)} bytes")
```

If conversion fails or produces 0 bytes, the issue is in audio conversion.

**Fix for audio conversion:**
```python
# Ensure audioop is imported correctly
import audioop

def pcm16_to_mulaw(pcm_data: bytes) -> bytes:
    """Convert OpenAI PCM16 to Twilio mulaw"""
    if not pcm_data:
        return b''
    try:
        return audioop.lin2ulaw(pcm_data, 2)
    except Exception as e:
        print(f"Audio conversion error: {e}")
        return b''
```

#### Step 3: Verify Sending to Twilio
```python
# Add debug logging to voice_handler.py around line 184

# Send to Twilio
await twilio_ws.send(json.dumps({
    "event": "media",
    "media": {
        "payload": encode_base64(mulaw_data)
    }
}))
print(f"[{call_sid}] 📤 Sent {len(mulaw_data)} bytes to Twilio")
```

If you see `📤 Sent` but still no audio, the issue is with Twilio.

**Fix for Twilio:**

1. Check Twilio expects this format:
```json
{
  "event": "media",
  "streamSid": "MZ...",  // Optional
  "media": {
    "payload": "base64_encoded_mulaw_data"
  }
}
```

2. Try adding streamSid:
```python
# In voice_handler.py, store streamSid from start event
# Then include it in media messages:
await twilio_ws.send(json.dumps({
    "event": "media",
    "streamSid": self.stream_sid,  # Add this
    "media": {
        "payload": encode_base64(mulaw_data)
    }
}))
```

### Issue 4: Initial Greeting Not Playing

**Symptoms:**
- Call connects
- Assistant greets in logs
- But customer hears silence initially

**Cause:**
OpenAI Realtime needs time to initialize before sending audio.

**Fix:**

Add a delay before initial greeting:
```python
# In voice_handler.py, connect method, after session.update:

await asyncio.sleep(0.5)  # Wait for session to be ready

# Then send greeting
await ws.send(json.dumps({
    "type": "response.create",
    "response": {
        "modalities": ["audio"],
        "instructions": "Say this: Hello! How can I help you today?"
    }
}))
```

## Enhanced Debugging

### Enable Verbose Logging

Add this to `voice_handler.py` at the top:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Log All WebSocket Messages

```python
# In _stream_agent_audio method:
async for message in openai_ws:
    print(f"[{call_sid}] 📨 OpenAI event: {message[:200]}")  # First 200 chars
    data = json.loads(message)
    # ... rest of code
```

### Test Audio Locally

Create a test script to verify audio conversion:
```python
import audioop
import base64

# Create test PCM16 audio (silence)
pcm_data = b'\x00\x00' * 1000  # 1000 samples of silence

# Convert to mulaw
mulaw_data = audioop.lin2ulaw(pcm_data, 2)

# Encode to base64
encoded = base64.b64encode(mulaw_data).decode('utf-8')

print(f"PCM: {len(pcm_data)} bytes")
print(f"mulaw: {len(mulaw_data)} bytes")
print(f"base64: {len(encoded)} chars")
print(f"Conversion working: {len(mulaw_data) > 0}")
```

## Testing Strategy

1. **Test Audio In (Customer → System)**
   - Call the number
   - Say "Hello"
   - Check logs for transcription
   - ✓ If you see transcription, audio IN is working

2. **Test Assistant Processing**
   - After saying "Hello"
   - Check logs for Assistant response
   - ✓ If you see response text, processing is working

3. **Test Audio Out (System → Customer)**
   - After Assistant responds
   - Listen for audio
   - Check logs for audio delta events
   - ✓ If you hear audio, complete flow works

## Expected Log Output (Success)

```
[CAxxxxx] Incoming call from +1234567890
[CAxxxxx] Media stream started
[CAxxxxx] Connected to OpenAI Realtime
[CAxxxxx] 🔊 Received audio delta: 1024 bytes
[CAxxxxx] 📦 PCM data: 1024 bytes
[CAxxxxx] 📦 mulaw data: 512 bytes
[CAxxxxx] 📤 Sent 512 bytes to Twilio
[CAxxxxx] Customer said: Hello
[CAxxxxx] → Assistant: Hello
[CAxxxxx] Run status: in_progress
[CAxxxxx] Run status: completed
[CAxxxxx] ← Assistant: Hello! How can I help you today?
[CAxxxxx] 🔊 Received audio delta: 2048 bytes
[CAxxxxx] 📦 PCM data: 2048 bytes
[CAxxxxx] 📦 mulaw data: 1024 bytes
[CAxxxxx] 📤 Sent 1024 bytes to Twilio
...
```

## Still Not Working?

If you've tried everything above and still no audio:

1. **Verify OpenAI API has Realtime access**
   - Some keys don't have Realtime API enabled
   - Contact OpenAI support if needed

2. **Test with a minimal example**
   - Use OpenAI's official Realtime example
   - If that doesn't work, issue is with OpenAI setup

3. **Check Twilio Media Streams documentation**
   - https://www.twilio.com/docs/voice/twiml/stream
   - Ensure your implementation matches their spec

4. **Try a different approach**
   - Instead of streaming, use Twilio's `<Say>` verb for testing
   - Confirms Twilio itself works

## Quick Fix Script

Run this to add comprehensive debugging:

```bash
# Backup current file
cp voice_handler.py voice_handler.py.backup

# Add debugging (manually edit voice_handler.py)
# Add print statements at each step as shown above
```

## Contact for Help

If still stuck, provide:
1. Server logs (with [call_sid] prefix)
2. OpenAI API key status (has Realtime access?)
3. Twilio webhook configuration
4. Network setup (local/deployed, ngrok, etc.)
