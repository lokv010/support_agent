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
