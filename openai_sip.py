"""
OpenAI SIP Integration - Replaces Twilio for incoming call handling.

Uses OpenAI Realtime API with SIP trunking:
- Webhook-based call routing (incoming calls via POST)
- HMAC-SHA256 signature verification
- Session config with voice model, tools, and MCP servers
- Call lifecycle management (accept, reject, hangup, transfer)
"""

import base64
import hashlib
import hmac
import json
import time
import os
from datetime import datetime, timezone
from typing import Optional

import aiohttp
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_WEBHOOK_SECRET = os.getenv("OPENAI_WEBHOOK_SECRET", "")
OPENAI_REALTIME_BASE = "https://api.openai.com/v1/realtime"
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:3100/mcp")

# Maximum allowed age for webhook timestamps (5 minutes)
WEBHOOK_TIMESTAMP_TOLERANCE = 300

# ---------------------------------------------------------------------------
# In-memory call record store
# ---------------------------------------------------------------------------
_active_calls: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# 1. verify_webhook_signature
# ---------------------------------------------------------------------------
def _get_header(headers: dict, name: str) -> str:
    """Case-insensitive header lookup.

    Quart/Werkzeug title-cases headers when converted to dict
    (e.g. ``Webhook-Signature``), but the spec uses lowercase.
    """
    # Try exact, then Title-Case, then iterate
    for key in (name, name.title(), name.upper()):
        if key in headers:
            return headers[key]
    # Fallback: brute-force case-insensitive scan
    lower = name.lower()
    for key, value in headers.items():
        if key.lower() == lower:
            return value
    return ""


def verify_webhook_signature(headers: dict, body: bytes) -> bool:
    """Validate that the incoming webhook request is genuinely from OpenAI.

    OpenAI uses the `Standard Webhooks <https://www.standardwebhooks.com>`_
    specification (Svix).  Three headers are required:

    - ``webhook-id``        – unique delivery ID
    - ``webhook-timestamp`` – Unix epoch seconds
    - ``webhook-signature`` – ``v1,<base64-HMAC-SHA256>``

    The signed content is ``{webhook_id}.{webhook_timestamp}.{body}``.
    The signing key is the base64-decoded portion of the secret **after**
    stripping the ``whsec_`` prefix.

    Args:
        headers: Raw request headers (dict-like).
        body: Raw request body as bytes.

    Returns:
        True if the signature is valid and timestamp is fresh, False otherwise.
    """
    if not OPENAI_WEBHOOK_SECRET:
        print("[SIP] WARNING: OPENAI_WEBHOOK_SECRET not set – skipping verification")
        return True

    webhook_id = _get_header(headers, "webhook-id")
    timestamp = _get_header(headers, "webhook-timestamp")
    signature = _get_header(headers, "webhook-signature")

    if not webhook_id or not timestamp or not signature:
        print(
            f"[SIP] Missing required webhook headers "
            f"(id={bool(webhook_id)}, ts={bool(timestamp)}, sig={bool(signature)})"
        )
        return False

    # Replay-attack protection
    try:
        ts = int(timestamp)
        now = int(time.time())
        if abs(now - ts) > WEBHOOK_TIMESTAMP_TOLERANCE:
            print(f"[SIP] Webhook timestamp too old: {abs(now - ts)}s drift")
            return False
    except ValueError:
        print("[SIP] Invalid webhook-timestamp value")
        return False

    # Derive the signing key: base64-decode the part after "whsec_"
    secret_str = OPENAI_WEBHOOK_SECRET
    if secret_str.startswith("whsec_"):
        secret_str = secret_str[len("whsec_"):]
    try:
        secret_bytes = base64.b64decode(secret_str)
    except Exception:
        print("[SIP] Failed to base64-decode webhook secret")
        return False

    # Signed content: "{webhook_id}.{timestamp}.{body}"
    signed_content = f"{webhook_id}.{timestamp}.".encode() + body

    expected_sig = base64.b64encode(
        hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
    ).decode()

    # The header may contain space-separated signatures: "v1,<sig1> v1,<sig2>"
    for sig_part in signature.split(" "):
        sig_part = sig_part.strip()
        if not sig_part:
            continue
        # Strip version prefix "v1,"
        if sig_part.startswith("v1,"):
            sig_value = sig_part[3:]
        else:
            sig_value = sig_part

        if hmac.compare_digest(expected_sig, sig_value):
            return True

    print("[SIP] Webhook signature mismatch")
    return False


# ---------------------------------------------------------------------------
# 2. handle_webhook
# ---------------------------------------------------------------------------
async def handle_webhook(headers: dict, body: bytes) -> tuple[dict, int]:
    """Main entry point for all incoming OpenAI webhook events.

    Verifies the signature, extracts the event type, and routes to the
    appropriate handler.

    Args:
        headers: Request headers.
        body: Raw request body bytes.

    Returns:
        Tuple of (response_dict, http_status_code).
    """
    # Verify authenticity
    if not verify_webhook_signature(headers, body):
        return {"error": "Invalid signature"}, 401

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON"}, 400

    event_type = payload.get("type", "")
    print(f"\n[SIP] Webhook event: {event_type}")

    if event_type == "realtime.call.incoming":
        return await _handle_incoming_call(payload)
    else:
        log_event(event_type, payload)
        return {"status": "event_logged", "type": event_type}, 200


# ---------------------------------------------------------------------------
# 3. build_session_config
# ---------------------------------------------------------------------------
def build_session_config(
    caller_number: str = "",
    sip_headers: Optional[dict] = None,
) -> dict:
    """Construct the session configuration for an accepted call.

    Assembles model, voice, instructions, tools, MCP servers, turn detection,
    and temperature.  Optionally customises instructions based on caller number.

    Args:
        caller_number: The caller's phone number (E.164).
        sip_headers: Additional SIP headers from the incoming INVITE.

    Returns:
        Complete session configuration dict ready for the accept endpoint.
    """
    instructions = (
        "You are Sarah, a friendly customer support agent for Elite Auto Service Center.\n\n"
        "PERSONALITY:\n"
        "- Warm but efficient\n"
        "- Concise (1-2 sentences when possible)\n"
        "- Never robotic or overly formal\n"
        "- Keep conversations focused and helpful\n\n"
        "YOUR ROLE:\n"
        "Help customers schedule appointments and resolve issues efficiently over the phone.\n\n"
        "CRITICAL PHONE RULES:\n"
        "- Maximum 20 words per response\n"
        "- ONE question at a time\n"
        "- Natural conversational speech\n"
        "- No formatting, bullets, or lists or emojis\n\n"
        "CONVERSATION FLOW:\n"
        "1. Greet the customer warmly\n"
        "2. Ask for phone number, then call check_customer_history\n"
        "3. If existing customer: greet by name and ask what service they need\n"
        "   If new customer: collect details (make, model, km, name, email) then call add_customer_record\n"
        "4. Get service details, call get_service_pricing, quote the price\n"
        "5. When ready to schedule, call check_availability and offer 2-3 options\n"
        "6. Confirm details and call create_event only after explicit customer confirmation\n\n"
        "CRITICAL RULES:\n"
        "- NEVER make up prices\n"
        "- NEVER book without confirmation\n"
        "- ALWAYS keep responses under 20 words\n"
        "- ONE question per response\n"
        "- Use natural phone speech"
    )

    # Customize for known VIP callers (example)
    if caller_number and sip_headers:
        vip_header = (sip_headers or {}).get("X-VIP", "")
        if vip_header == "true":
            instructions += "\n\nThis is a VIP customer. Prioritize their requests."

    # Tool definitions for OpenAI Realtime function calling
    tools = [
        {
            "type": "function",
            "function": {
                "name": "check_customer_history",
                "description": "Check customer history by phone number. Call this immediately when you get the customer's phone number.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone_number": {
                            "type": "string",
                            "description": "Customer phone number in E.164 format",
                        }
                    },
                    "required": ["phone_number"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "add_customer_record",
                "description": "Add a new customer record to the CRM. Use for new customers after getting name and email.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "make": {"type": "string", "description": "Vehicle make"},
                        "model": {"type": "string", "description": "Vehicle model"},
                        "kilometers": {"type": "string", "description": "Vehicle mileage in km"},
                        "name": {"type": "string", "description": "Customer full name"},
                        "email": {"type": "string", "description": "Customer email"},
                        "phone": {"type": "string", "description": "Customer phone number"},
                        "issue": {"type": "string", "description": "Service issue description"},
                        "status": {"type": "string", "description": "Record status (open/closed)"},
                        "priority": {"type": "string", "description": "Priority level (low/medium/high)"},
                        "notes": {"type": "string", "description": "Additional notes"},
                    },
                    "required": ["make", "model", "kilometers", "name", "email"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_service_pricing",
                "description": "Get pricing for a car service. Never guess prices, always call this tool.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_type": {
                            "type": "string",
                            "description": "Type of service (oil change, brake service, etc.)",
                        },
                        "vehicle_type": {
                            "type": "string",
                            "description": "Vehicle type (sedan, SUV, truck)",
                        },
                    },
                    "required": ["service_type", "vehicle_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_availability",
                "description": "Get available appointment time slots. Call when customer wants to schedule.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_type_uri": {
                            "type": "string",
                            "description": "Calendly event type URI",
                        },
                        "start_time": {
                            "type": "string",
                            "description": "Start of availability window (ISO 8601)",
                        },
                        "end_time": {
                            "type": "string",
                            "description": "End of availability window (ISO 8601)",
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_event",
                "description": "Create an appointment booking. Only call after explicit customer confirmation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "eventTypeUri": {"type": "string", "description": "Calendly event type URI"},
                        "customerName": {"type": "string", "description": "Customer full name"},
                        "customerEmail": {"type": "string", "description": "Customer email"},
                        "customerPhone": {"type": "string", "description": "Customer phone number"},
                        "preferredDate": {"type": "string", "description": "Preferred date/time (ISO 8601)"},
                    },
                    "required": ["eventTypeUri", "customerName", "customerEmail", "customerPhone", "preferredDate"],
                },
            },
        },
    ]

    session_config = {
        "model": "gpt-4o-realtime-preview",
        "voice": "coral",
        "instructions": instructions,
        "tools": tools,
        "mcp_servers": [
            {
                "url": MCP_SERVER_URL,
                "allowed_tools": [
                    "check_customer_history",
                    "add_customer_record",
                    "get_service_pricing",
                    "check_availability",
                    "create_event",
                ],
            }
        ],
        "turn_detection": {
            "type": "semantic_vad",
        },
        "temperature": 0.7,
        "input_audio_format": "g711_ulaw",
        "output_audio_format": "g711_ulaw",
    }

    return session_config


# ---------------------------------------------------------------------------
# 4. accept_call
# ---------------------------------------------------------------------------
async def accept_call(call_id: str, sip_headers: Optional[dict] = None) -> dict:
    """Tell OpenAI to accept an incoming call and start a realtime session.

    Builds the session configuration and POSTs to the accept endpoint.

    Args:
        call_id: The call ID from the webhook payload.
        sip_headers: SIP headers from the INVITE (may contain caller info).

    Returns:
        OpenAI API response dict.
    """
    caller_number = ""
    if sip_headers:
        caller_number = sip_headers.get("From", "")

    session_config = build_session_config(caller_number, sip_headers)
    url = f"{OPENAI_REALTIME_BASE}/calls/{call_id}/accept"

    print(f"[SIP] Accepting call {call_id} from {caller_number or 'unknown'}")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            json=session_config,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
        ) as resp:
            resp_data = await resp.json() if resp.status == 200 else {"error": await resp.text()}
            print(f"[SIP] Accept response ({resp.status}): {json.dumps(resp_data)[:300]}")

    # Track the call
    create_call_record(call_id, caller_number, datetime.now(timezone.utc).isoformat())

    return resp_data


# ---------------------------------------------------------------------------
# 5. reject_call
# ---------------------------------------------------------------------------
async def reject_call(call_id: str, status_code: int = 603, reason: str = "Declined") -> dict:
    """Decline an incoming call.

    Use cases: unknown/blocked numbers, maintenance mode, rate limiting.

    Args:
        call_id: The call ID to reject.
        status_code: SIP status code (default 603 = Decline).
        reason: Human-readable rejection reason for logging.

    Returns:
        OpenAI API response dict.
    """
    url = f"{OPENAI_REALTIME_BASE}/calls/{call_id}/reject"

    print(f"[SIP] Rejecting call {call_id} (SIP {status_code}): {reason}")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            json={"status_code": status_code},
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
        ) as resp:
            resp_data = await resp.json() if resp.status == 200 else {"error": await resp.text()}
            print(f"[SIP] Reject response ({resp.status}): {json.dumps(resp_data)[:300]}")

    return resp_data


# ---------------------------------------------------------------------------
# 6. hangup_call
# ---------------------------------------------------------------------------
async def hangup_call(call_id: str, reason: str = "Normal") -> dict:
    """Programmatically end an active call.

    Use cases: max duration exceeded, abuse detected, system shutdown.

    Args:
        call_id: The call ID to hang up.
        reason: Reason for hanging up (for logging).

    Returns:
        OpenAI API response dict.
    """
    url = f"{OPENAI_REALTIME_BASE}/calls/{call_id}/hangup"

    print(f"[SIP] Hanging up call {call_id}: {reason}")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            json={},
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
        ) as resp:
            resp_data = await resp.json() if resp.status == 200 else {"error": await resp.text()}
            print(f"[SIP] Hangup response ({resp.status}): {json.dumps(resp_data)[:300]}")

    # Remove call record
    destroy_call_record(call_id)

    return resp_data


# ---------------------------------------------------------------------------
# 7. transfer_call
# ---------------------------------------------------------------------------
async def transfer_call(call_id: str, target_uri: str) -> dict:
    """Transfer an active call to another agent or number (SIP REFER).

    Args:
        call_id: The call ID to transfer.
        target_uri: Transfer destination. Formats:
            - ``tel:+14155550123`` for PSTN numbers
            - ``sip:agent@example.com`` for SIP endpoints

    Returns:
        OpenAI API response dict.
    """
    url = f"{OPENAI_REALTIME_BASE}/calls/{call_id}/refer"

    print(f"[SIP] Transferring call {call_id} → {target_uri}")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            json={"target_uri": target_uri},
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
        ) as resp:
            resp_data = await resp.json() if resp.status == 200 else {"error": await resp.text()}
            print(f"[SIP] Transfer response ({resp.status}): {json.dumps(resp_data)[:300]}")

    return resp_data


# ---------------------------------------------------------------------------
# 8. create_call_record / destroy_call_record
# ---------------------------------------------------------------------------
def create_call_record(call_id: str, caller_number: str, timestamp: str) -> dict:
    """Track an active call in the in-memory store.

    Args:
        call_id: Unique call identifier from OpenAI.
        caller_number: Caller's phone number.
        timestamp: ISO 8601 timestamp of call start.

    Returns:
        The created call record dict.
    """
    record = {
        "call_id": call_id,
        "caller_number": caller_number,
        "started_at": timestamp,
        "status": "active",
    }
    _active_calls[call_id] = record
    print(f"[SIP] Call record created: {call_id} ({caller_number})")
    return record


def destroy_call_record(call_id: str) -> bool:
    """Remove a call record from the in-memory store.

    Args:
        call_id: The call ID to remove.

    Returns:
        True if the record existed and was removed, False otherwise.
    """
    if call_id in _active_calls:
        del _active_calls[call_id]
        print(f"[SIP] Call record destroyed: {call_id}")
        return True
    print(f"[SIP] No call record found for: {call_id}")
    return False


def get_active_calls() -> dict[str, dict]:
    """Return a copy of all active call records."""
    return dict(_active_calls)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
async def _handle_incoming_call(payload: dict) -> tuple[dict, int]:
    """Handle a ``realtime.call.incoming`` event.

    Extracts call metadata and accepts the call. Returns 200 immediately
    as OpenAI expects a fast response.

    Args:
        payload: The full webhook event payload.

    Returns:
        Tuple of (response_dict, http_status_code).
    """
    call_data = payload.get("call", {})
    call_id = call_data.get("id", "")
    sip_headers = call_data.get("sip_headers", {})
    caller_number = call_data.get("caller_number", sip_headers.get("From", "unknown"))

    print(f"\n{'='*60}")
    print(f"[SIP] INCOMING CALL: {call_id}")
    print(f"[SIP] From: {caller_number}")
    print(f"[SIP] SIP Headers: {json.dumps(sip_headers)[:200]}")
    print(f"{'='*60}\n")

    # Accept the call (runs in background – we return 200 immediately)
    try:
        result = await accept_call(call_id, sip_headers)
        return {"status": "accepted", "call_id": call_id, "result": result}, 200
    except Exception as e:
        print(f"[SIP] Error accepting call {call_id}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "call_id": call_id, "error": str(e)}, 200


def log_event(event_type: str, payload: dict) -> None:
    """Log an unhandled webhook event for debugging.

    Args:
        event_type: The event type string.
        payload: Full event payload.
    """
    print(f"[SIP] Event logged: {event_type}")
    print(f"[SIP] Payload: {json.dumps(payload)[:500]}")
