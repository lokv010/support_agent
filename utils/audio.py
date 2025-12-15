"""Audio conversion utilities for Twilio and OpenAI Realtime API."""

import base64
import audioop


def mulaw_to_pcm16(mulaw_data: bytes) -> bytes:
    """
    Convert mulaw audio to PCM16 format.

    Twilio sends audio in mulaw format, OpenAI Realtime expects PCM16.

    Args:
        mulaw_data: Audio data in mulaw format

    Returns:
        Audio data in PCM16 format
    """
    return audioop.ulaw2lin(mulaw_data, 2)


def pcm16_to_mulaw(pcm_data: bytes) -> bytes:
    """
    Convert PCM16 audio to mulaw format.

    OpenAI Realtime sends audio in PCM16, Twilio expects mulaw.

    Args:
        pcm_data: Audio data in PCM16 format

    Returns:
        Audio data in mulaw format
    """
    return audioop.lin2ulaw(pcm_data, 2)


def encode_audio_base64(audio_data: bytes) -> str:
    """
    Encode audio data to base64 string.

    Args:
        audio_data: Raw audio bytes

    Returns:
        Base64 encoded string
    """
    return base64.b64encode(audio_data).decode('utf-8')


def decode_audio_base64(encoded_data: str) -> bytes:
    """
    Decode base64 audio string to bytes.

    Args:
        encoded_data: Base64 encoded audio string

    Returns:
        Raw audio bytes
    """
    return base64.b64decode(encoded_data)


def validate_audio_format(data: bytes, expected_size: int = None) -> bool:
    """
    Validate audio data format.

    Args:
        data: Audio data to validate
        expected_size: Expected size in bytes (optional)

    Returns:
        True if valid, False otherwise
    """
    if not data or len(data) == 0:
        return False

    if expected_size and len(data) != expected_size:
        return False

    return True
