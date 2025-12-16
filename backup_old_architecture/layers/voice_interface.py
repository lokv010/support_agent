"""Voice interface layer using OpenAI Realtime API."""

import asyncio
import json
import websockets
from typing import Optional, Callable
from config.settings import config
from utils.audio import mulaw_to_pcm16, pcm16_to_mulaw, encode_audio_base64, decode_audio_base64
from utils.logger import setup_logger, ContextLogger

logger = setup_logger(__name__)


class VoiceInterfaceHandler:
    """Handler for OpenAI Realtime API voice interface."""

    REALTIME_CONFIG = {
        "modalities": ["text", "audio"],
        "instructions": """You are a voice interface for a car service center.

Your ONLY job is:
1. Listen to customer speech and transcribe it accurately
2. Speak responses provided by the business system naturally and clearly

DO NOT make business decisions.
DO NOT access customer data yourself.
DO NOT schedule appointments yourself.

You will receive text responses to speak. Speak them naturally with a friendly, professional tone.""",
        "voice": config.OPENAI_VOICE,
        "input_audio_format": "pcm16",
        "output_audio_format": "pcm16",
        "input_audio_transcription": {"model": "whisper-1"},
        "turn_detection": {
            "type": "server_vad",
            "threshold": 0.5,
            "silence_duration_ms": 500
        },
        "tools": []  # NO business tools!
    }

    def __init__(self):
        self.openai_url = f"wss://api.openai.com/v1/realtime?model={config.OPENAI_REALTIME_MODEL}"
        self.api_key = config.OPENAI_API_KEY
        self.sessions = {}  # call_sid -> session data
        self.transcription_callback: Optional[Callable] = None

    def set_transcription_callback(self, callback: Callable):
        """Set callback function for transcription events."""
        self.transcription_callback = callback

    async def connect(self, call_sid: str) -> bool:
        """
        Connect to OpenAI Realtime API.

        Args:
            call_sid: Twilio call SID

        Returns:
            True if connected successfully
        """
        try:
            ctx_logger = ContextLogger(logger, call_sid=call_sid)
            ctx_logger.info("Connecting to OpenAI Realtime API")

            # Connect to OpenAI Realtime
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "OpenAI-Beta": "realtime=v1"
            }

            openai_ws = await websockets.connect(self.openai_url, extra_headers=headers)

            # Store session
            self.sessions[call_sid] = {
                'openai_ws': openai_ws,
                'twilio_ws': None,
                'logger': ctx_logger
            }

            # Configure session
            await self._configure_session(call_sid)

            ctx_logger.info("Connected to OpenAI Realtime API")
            return True

        except Exception as e:
            logger.error(f"[{call_sid}] Failed to connect to OpenAI Realtime: {e}")
            return False

    async def _configure_session(self, call_sid: str):
        """Configure OpenAI Realtime session."""
        session = self.sessions.get(call_sid)
        if not session:
            return

        openai_ws = session['openai_ws']

        # Send session configuration
        config_event = {
            "type": "session.update",
            "session": self.REALTIME_CONFIG
        }

        await openai_ws.send(json.dumps(config_event))
        session['logger'].debug("Sent session configuration")

    async def handle_media_stream(self, twilio_ws, call_sid: str):
        """
        Main handler for bidirectional media streaming.

        Args:
            twilio_ws: Twilio WebSocket connection
            call_sid: Call SID
        """
        session = self.sessions.get(call_sid)
        if not session:
            logger.error(f"[{call_sid}] No session found for media stream")
            return

        session['twilio_ws'] = twilio_ws
        ctx_logger = session['logger']

        try:
            # Start both processing tasks concurrently
            await asyncio.gather(
                self._process_twilio_audio(call_sid),
                self._process_openai_events(call_sid)
            )
        except Exception as e:
            ctx_logger.error(f"Error in media stream handler: {e}")
        finally:
            await self.disconnect(call_sid)

    async def _process_twilio_audio(self, call_sid: str):
        """
        Process audio from Twilio (customer speech).

        Args:
            call_sid: Call SID
        """
        session = self.sessions.get(call_sid)
        if not session:
            return

        twilio_ws = session['twilio_ws']
        openai_ws = session['openai_ws']
        ctx_logger = session['logger']

        try:
            async for message in twilio_ws:
                data = json.loads(message)
                event_type = data.get('event')

                if event_type == 'media':
                    # Get audio payload
                    media = data.get('media', {})
                    audio_payload = media.get('payload')

                    if audio_payload:
                        # Convert mulaw to PCM16
                        mulaw_data = decode_audio_base64(audio_payload)
                        pcm16_data = mulaw_to_pcm16(mulaw_data)
                        pcm16_base64 = encode_audio_base64(pcm16_data)

                        # Send to OpenAI
                        audio_event = {
                            "type": "input_audio_buffer.append",
                            "audio": pcm16_base64
                        }
                        await openai_ws.send(json.dumps(audio_event))

                elif event_type == 'stop':
                    ctx_logger.info("Twilio stream stopped")
                    break

        except Exception as e:
            ctx_logger.error(f"Error processing Twilio audio: {e}")

    async def _process_openai_events(self, call_sid: str):
        """
        Process events from OpenAI Realtime.

        Args:
            call_sid: Call SID
        """
        session = self.sessions.get(call_sid)
        if not session:
            return

        openai_ws = session['openai_ws']
        twilio_ws = session['twilio_ws']
        ctx_logger = session['logger']

        try:
            async for message in openai_ws:
                event = json.loads(message)
                event_type = event.get('type')

                if event_type == 'response.audio.delta':
                    # Stream audio back to Twilio
                    delta = event.get('delta')
                    if delta:
                        # Convert PCM16 to mulaw
                        pcm16_data = decode_audio_base64(delta)
                        mulaw_data = pcm16_to_mulaw(pcm16_data)
                        mulaw_base64 = encode_audio_base64(mulaw_data)

                        # Send to Twilio
                        twilio_event = {
                            "event": "media",
                            "streamSid": call_sid,
                            "media": {
                                "payload": mulaw_base64
                            }
                        }
                        await twilio_ws.send(json.dumps(twilio_event))

                elif event_type == 'conversation.item.input_audio_transcription.completed':
                    # Customer speech transcribed
                    transcript = event.get('transcript', '')
                    if transcript and self.transcription_callback:
                        ctx_logger.info(f"Customer: {transcript}")
                        await self.transcription_callback(call_sid, transcript)

                elif event_type == 'error':
                    error = event.get('error', {})
                    ctx_logger.error(f"OpenAI Realtime error: {error}")

        except Exception as e:
            ctx_logger.error(f"Error processing OpenAI events: {e}")

    async def send_text_response(self, call_sid: str, text: str):
        """
        Send text to be spoken by OpenAI Realtime.

        Args:
            call_sid: Call SID
            text: Text to speak
        """
        session = self.sessions.get(call_sid)
        if not session:
            logger.error(f"[{call_sid}] No session found for text response")
            return

        openai_ws = session['openai_ws']
        ctx_logger = session['logger']

        try:
            # Send text response to be spoken
            response_event = {
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": f"Say this to the customer: {text}"
                }
            }

            await openai_ws.send(json.dumps(response_event))
            ctx_logger.info(f"Agent: {text}")

        except Exception as e:
            ctx_logger.error(f"Error sending text response: {e}")

    async def disconnect(self, call_sid: str):
        """
        Disconnect and cleanup session.

        Args:
            call_sid: Call SID
        """
        session = self.sessions.get(call_sid)
        if not session:
            return

        ctx_logger = session['logger']

        try:
            # Close OpenAI WebSocket
            openai_ws = session.get('openai_ws')
            if openai_ws:
                await openai_ws.close()

            # Remove session
            del self.sessions[call_sid]

            ctx_logger.info("Voice interface disconnected")

        except Exception as e:
            ctx_logger.error(f"Error during disconnect: {e}")
