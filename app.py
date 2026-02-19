"""
Voice Agent - OpenAI SIP Integration Architecture

Uses:
- OpenAI Realtime API with SIP trunking for incoming calls
- OpenAI Realtime voice model for conversation (speech-to-speech)
- MCP server for CRM tool integration (Zapier)

Replaces Twilio: no TwiML, no Gather, no Twilio SDK.
OpenAI handles STT, TTS, and conversation natively via the Realtime API.
"""

from quart import Quart, request, jsonify
import os
from dotenv import load_dotenv

from openai_sip import (
    handle_webhook,
    reject_call,
    hangup_call,
    transfer_call,
    get_active_calls,
)

# Load environment
load_dotenv()

# Initialize Quart
app = Quart(__name__)

print("=" * 70)
print("VOICE AGENT SYSTEM STARTED - OPENAI SIP")
print("=" * 70)
print("Using: OpenAI Realtime API + SIP Trunking + MCP Tools")
print("=" * 70)


# ---------------------------------------------------------------------------
# Webhook endpoint — receives all events from OpenAI
# ---------------------------------------------------------------------------
@app.route("/webhook", methods=["POST"])
async def webhook():
    """
    Main webhook endpoint for OpenAI SIP events.

    OpenAI sends POST requests here for:
    - realtime.call.incoming  → routed to accept_call
    - Other event types       → logged

    The webhook signature is verified before processing.
    """
    body = await request.get_data()
    headers = dict(request.headers)

    response_data, status_code = await handle_webhook(headers, body)
    return jsonify(response_data), status_code


# ---------------------------------------------------------------------------
# Management endpoints — for programmatic call control
# ---------------------------------------------------------------------------
@app.route("/calls/<call_id>/reject", methods=["POST"])
async def api_reject_call(call_id: str):
    """
    Reject an incoming call.

    Optional JSON body:
        { "status_code": 603, "reason": "Maintenance" }
    """
    data = await request.get_json(silent=True) or {}
    status_code = data.get("status_code", 603)
    reason = data.get("reason", "Declined")

    result = await reject_call(call_id, status_code=status_code, reason=reason)
    return jsonify(result), 200


@app.route("/calls/<call_id>/hangup", methods=["POST"])
async def api_hangup_call(call_id: str):
    """
    Hang up an active call.

    Optional JSON body:
        { "reason": "Max duration exceeded" }
    """
    data = await request.get_json(silent=True) or {}
    reason = data.get("reason", "Normal")

    result = await hangup_call(call_id, reason=reason)
    return jsonify(result), 200


@app.route("/calls/<call_id>/transfer", methods=["POST"])
async def api_transfer_call(call_id: str):
    """
    Transfer an active call to another number or SIP endpoint.

    Required JSON body:
        { "target_uri": "tel:+14155550123" }
        or
        { "target_uri": "sip:agent@example.com" }
    """
    data = await request.get_json(silent=True) or {}
    target_uri = data.get("target_uri", "")

    if not target_uri:
        return jsonify({"error": "target_uri is required"}), 400

    result = await transfer_call(call_id, target_uri)
    return jsonify(result), 200


# ---------------------------------------------------------------------------
# Status & monitoring
# ---------------------------------------------------------------------------
@app.route("/calls", methods=["GET"])
async def list_calls():
    """List all active calls."""
    calls = get_active_calls()
    return jsonify({"active_calls": calls, "count": len(calls)}), 200


@app.route("/health", methods=["GET"])
async def health():
    """Health check."""
    calls = get_active_calls()
    return jsonify({
        "status": "healthy",
        "architecture": "openai_sip",
        "active_calls": len(calls),
    }), 200


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"Starting server on port {port}...")
    print(f"Webhook URL: POST /webhook")
    print(f"Management:  POST /calls/<id>/reject|hangup|transfer")
    print(f"Monitoring:  GET  /calls | GET /health")
    app.run(host="0.0.0.0", port=port)
