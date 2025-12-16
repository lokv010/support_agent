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
                },
                "input_audio_transcription": {
                    "model": "whisper-1"
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
        try:
            while True:
                message = await twilio_ws.receive()
                if message is None:
                    break

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

                elif data.get('event') == 'stop':
                    break

        except Exception as e:
            print(f"[{call_sid}] Customer audio error: {e}")

    async def _stream_agent_audio(self, call_sid: str, twilio_ws, openai_ws):
        """
        Stream agent audio: OpenAI Realtime → Twilio
        AND handle transcriptions → workflow
        """
        try:
            async for message in openai_ws:
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
