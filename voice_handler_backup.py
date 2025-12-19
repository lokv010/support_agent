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
from flask import logging
import websockets
import os
import audioop
import base64

# Audio conversion utilities
def encode_base64(data: bytes) -> str:
    """Encode to base64 string"""
    return base64.b64encode(data).decode('utf-8')

def decode_base64(data: str) -> bytes:
    """Decode from base64 string"""
    return base64.b64decode(data)

def mulaw_to_pcm16(mulaw_data: bytes) -> bytes:
    """Convert Twilio mulaw to OpenAI PCM16"""
    return audioop.ulaw2lin(mulaw_data, 2)

def pcm16_to_mulaw(pcm_data: bytes) -> bytes:
    """Convert OpenAI PCM16 to Twilio mulaw"""
    return audioop.lin2ulaw(pcm_data, 2)

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
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "input_audio_transcription": {
                    "model": "whisper-1"
                },
                "turn_detection":{
                    "type": "server_vad",
                    "threshold":0.5,
                    "silence_duration_ms":700,
                    "prefix_padding_ms":300
                }
            }
        }))

        timeout = 5  # seconds
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                data = json.loads(message)
                
                if data.get('type') == 'session.updated':
                    print(f"[{call_sid}] Session configured successfully")
                    break
                elif data.get('type') == 'error':
                    print(f"[{call_sid}] Session config error: {data.get('error')}")
                    raise Exception(f"Session config failed: {data.get('error')}")
            except asyncio.TimeoutError:
                continue

        print(f"[{call_sid}] Connected to OpenAI Realtime")
        await ws.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": "greet the customer and ask how you can help them."
                    }
                ]
            }
        }))

        # ✅ ADD: Then trigger response
        await ws.send(json.dumps({
            "type": "response.create",
            "response": {"modalities": ["audio", "text"]}
        }))


    async def handle_call(self, call_sid: str, stream_sid: str, twilio_ws):
        """
        Handle complete call

        This manages the audio streams and connects to workflow
        """
        # Connect to OpenAI
        await self.connect(call_sid)
        openai_ws = self.connections[call_sid]
        self.stream_sids=getattr(self,'stream_sids',{})
        self.stream_sids[call_sid]=stream_sid
        # Create workflow thread
        await self.workflow_client.create_thread(call_sid)

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
        try:
            while True:
                message = await twilio_ws.receive()
                if message is None:
                    print(f"[{call_sid}] Customer WebSocket closed")
                    break

                data = json.loads(message)
                event=data.get('event') 
                if event == 'media':
                    audio_payload = data['media']['payload']  
                    # Send to OpenAI
                    await openai_ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": audio_payload
                    }))
        except Exception as e:
            print(f"[{call_sid}] Customer audio error: {e}")

    async def _stream_agent_audio(self, call_sid: str, twilio_ws, openai_ws):
        """
        Stream agent audio: OpenAI Realtime → Twilio
        AND handle transcriptions → workflow
        """
        stream_sid = self.stream_sids.get(call_sid)
        audio_started = False
        
        try:
            async for message in openai_ws:
                data = json.loads(message)
                event_type = data.get('type')

                # ✅ Log important events for debugging
                if event_type in ['session.created', 'session.updated', 'response.created', 
                                'response.done', 'error']:
                    print(f"[{call_sid}] OpenAI event: {event_type}")
                    
                    if event_type == 'error':
                        error_message = data.get('error', {})
                        print(f"[{call_sid}] OpenAI Error: {error_message}")

                # ✅ Customer finished speaking - transcription ready
                if event_type == 'conversation.item.input_audio_transcription.completed':
                    transcript = data.get('transcript', '').strip()
                    
                    if transcript:
                        print(f"[{call_sid}] Customer said: {transcript}")
                        
                        # Send to workflow, get response
                        response_text = await self.workflow_client.send_message(
                            call_sid,
                            transcript
                        )
                        
                        print(f"[{call_sid}] Agent responding: {response_text}")
                        
                        # Tell OpenAI Realtime to speak the response
                        await openai_ws.send(json.dumps({
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "input_text",
                                        "text": response_text
                                    }
                                ]
                            }
                        }))
                        
                        # Trigger response
                        await openai_ws.send(json.dumps({
                            "type": "response.create",
                            "response": {"modalities": ["audio", "text"]}
                        }))

                # ✅ Agent audio output (this is what carries the voice)
                elif event_type == 'response.audio.delta':
                    if not audio_started:
                        print(f"[{call_sid}] Started streaming audio to customer")
                        audio_started = True
                    
                    # Get audio chunk (already in g711_ulaw base64 format)
                    audio_payload = data.get('delta', '')
                    
                    if audio_payload:
                        # Send to Twilio
                        await twilio_ws.send(json.dumps({
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {
                                "payload": audio_payload
                            }
                        }))
                
                # ✅ Audio response complete - send mark
                elif event_type == 'response.audio.done':
                    print(f"[{call_sid}] Audio response completed")
                    audio_started = False  # Reset for next response
                    
                    mark_id = f"mark_{int(asyncio.get_event_loop().time() * 1000)}"
                    await twilio_ws.send(json.dumps({
                        "event": "mark",
                        "streamSid": stream_sid,
                        "mark": {
                            "name": mark_id
                        }
                    }))

        except Exception as e:
            print(f"[{call_sid}] Agent audio error: {e}")
            import traceback
            traceback.print_exc()

    async def cleanup(self, call_sid: str):
        """Clean up connections"""
        if call_sid in self.connections:
            await self.connections[call_sid].close()
            del self.connections[call_sid]

        self.workflow_client.cleanup(call_sid)
        print(f"[{call_sid}] Call ended")
