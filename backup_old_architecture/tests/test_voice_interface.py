"""Tests for voice interface layer."""

import pytest
from utils.audio import mulaw_to_pcm16, pcm16_to_mulaw, encode_audio_base64, decode_audio_base64


def test_audio_conversion():
    """Test mulaw to PCM16 conversion."""
    # Create sample mulaw data
    mulaw_data = b'\x00\x01\x02\x03'

    # Convert to PCM16
    pcm_data = mulaw_to_pcm16(mulaw_data)
    assert isinstance(pcm_data, bytes)
    assert len(pcm_data) > 0

    # Convert back to mulaw
    converted_mulaw = pcm16_to_mulaw(pcm_data)
    assert isinstance(converted_mulaw, bytes)


def test_base64_encoding():
    """Test base64 encoding/decoding."""
    test_data = b'test audio data'

    # Encode
    encoded = encode_audio_base64(test_data)
    assert isinstance(encoded, str)

    # Decode
    decoded = decode_audio_base64(encoded)
    assert decoded == test_data
