"""
OpenAI SIP Integration - Replaces Twilio for incoming call handling.

Uses OpenAI Realtime API with SIP trunking:
- Webhook-based call routing (incoming calls via POST)
- HMAC-SHA256 signature verification
- Session config with voice model, tools, and MCP servers
- Call lifecycle management (accept, reject, hangup, transfer)
"""

import asyncio
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
import websockets

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_WEBHOOK_SECRET = os.getenv("OPENAI_WEBHOOK_SECRET", "")
OPENAI_REALTIME_BASE = "https://api.openai.com/v1/realtime"
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "https://silly-taxes-behave.loca.lt/mcp")

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
        "You are a friendly customer support agent for Elite Auto Service Center.\n\n"
        "PERSONALITY:\n"
        "- Customer should feel like they're talking to a helpful human, not a bot\n"
        "- Act more like human with emotions, expressions, and natural speech patterns\n"
        "- Use natural phone language (e.g. contractions, interjections)\n"
        "- Keep it natural and conversational\n"
        "- Never robotic or overly formal\n"
        "- Keep conversations focused and helpful\n\n"
        "YOUR ROLE:\n"
        "Help customers schedule appointments and resolve issues efficiently over the phone.\n\n"
    "=== ABSOLUTE RULES (NEVER VIOLATE) ===\n"
    "RULE 1: When customer says a phone number → IMMEDIATELY call check_customer_history. Do not say ANYTHING until you get the result.\n"
    "RULE 2: When customer mentions a service → IMMEDIATELY call get_service_pricing. Never quote prices without calling this.\n"
    "RULE 3: When customer wants to book → IMMEDIATELY call check_availability. Never suggest times without calling this.\n"
    "RULE 4: Maximum 15 words per response. ONE question at a time.\n"
    "RULE 5: Never say 'let me check' - just call the tool silently.\n\n"
    
    "=== CONVERSATION SCRIPT ===\n"
    "Step 1: Say 'Hi! This is Sarah from Elite Auto. What's your phone number?'\n"
    "Step 2: When they say a number → STOP TALKING → call check_customer_history(phone_number='their number')\n"
    "Step 3: After tool returns:\n"
    "  - If customer found: Say 'Hey [NAME]! How can I help with your [VEHICLE]?'\n"
    "  - If new customer: Say 'Thanks! What kind of vehicle do you have?'\n"
    "Step 4: When they mention service (oil change, brakes, etc) → STOP TALKING → call get_service_pricing(service_type='what they said', vehicle_type='sedan or suv or truck')\n"
    "Step 5: After tool returns: Say EXACTLY '[SERVICE] is [PRICE from tool]. Want to book it?'\n"
    "Step 6: If they say yes → STOP TALKING → call check_availability()\n"
    "Step 7: Read 2-3 times from tool result, ask 'Which works for you?'\n"
    "Step 8: After they pick → Say 'Confirming [DATE TIME] for [SERVICE]. Correct?'\n"
    "Step 9: If yes → call create_event with all details\n\n"
    
    "=== PHONE BEHAVIOR ===\n"
    "- Sound human, use fillers like 'um', 'uh' sparingly\n"
    "- Never robotic\n"
    "- Keep it brief and natural\n"
    )

    # Customize for known VIP callers (example)
    if caller_number and sip_headers:
        vip_header = (sip_headers or {}).get("X-VIP", "")
        if vip_header == "true":
            instructions += "\n\nThis is a VIP customer. Prioritize their requests."

    # Tool definitions for OpenAI Realtime function calling

    session_config = {
        "type":"realtime",
        "model": "gpt-realtime",
        "instructions": instructions,
        "tool_choice": "auto",
        "tools": [
        {
        "type": "mcp",                           
        "server_label": "crm-mcp-server",       
        "server_url": MCP_SERVER_URL,            
        "allowed_tools": [                       
            "check_customer_history",
            "add_customer_record",
            "get_service_pricing",
            "check_availability",
            "create_event"]
        }],
        
        "audio": {
        "input":  {"format": "g711_ulaw",
                              "turn_detection": {
                              "type": "semantic_vad",
                              }},
        "output": {"format": "g711_ulaw","voice": "alloy"},
    }
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
            try:
                resp_data = await resp.json()
            except Exception:
                resp_data = {"raw_error": await resp.text()}
            print(f"[SIP] Accept response ({resp.status}): {json.dumps(resp_data)[:300]}")

    # Track the call
    create_call_record(call_id, caller_number, datetime.now(timezone.utc).isoformat())

    return resp_data

# ═══════════════════════════════════════════════════════════
# Step 2: Monitoring (NOT tool execution)
# ═══════════════════════════════════════════════════════════

async def monitor_call(call_id: str):
    """
    Observe the call for logging/analytics.
    Tool execution happens automatically - you just watch.
    """
    ws_url = f"wss://api.openai.com/v1/realtime?call_id={call_id}"
    
    async with websockets.connect(
        ws_url,
        extra_headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}
    ) as ws:
        async for message in ws:
            event = json.loads(message)
            
            # Log all response events
            if event["type"].startswith("response."):
                print(f"[Call {call_id}] {event['type']}")
            # Specifically watch for tool calls
            if event["type"] == "response.function_call_arguments.done":
                print(f"✓✓✓ TOOL CALLED: {event['name']}")
                print(f"    Arguments: {event['arguments']}")

            if event["type"] == "response.function_call_arguments.error":
                print(f"✖️✖️✖️ TOOL CALL FAILED: {event['name']}")
                print(f"    Error: {event['error']}")

            if event["type"] == "conversation.item.created":
                item = event["item"]
                if item["type"] == "mcp_list_tools":
                    print(f"✓ MCP tools loaded: {item['content'][:200]}")
            
            # Check if model even TRIES to call tools
            if event["type"] == "response.output_item.added":
                item = event["item"]
                print(f"Response item type: {item['type']}") 
            # Watch for responses without tools
            if event["type"] == "response.done":
                output = event["response"]["output"]
                has_tool_call = any(
                    item.get("type") == "function_call" 
                    for item in output
                )
                if not has_tool_call:
                    print(f"⚠️ Response completed WITHOUT calling any tools")
                    print(f"   Output items: {[item['type'] for item in output]}")


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

    Payload structure::

        {
          "type": "realtime.call.incoming",
          "data": {
            "call_id": "...",
            "sip_headers": [
              {"name": "From", "value": "sip:+1234@..."},
              ...
            ]
          }
        }

    Args:
        payload: The full webhook event payload.

    Returns:
        Tuple of (response_dict, http_status_code).
    """
    data = payload.get("data", {})
    call_id = data.get("call_id", "")

    # Convert sip_headers from [{name, value}, ...] list to a flat dict
    raw_sip_headers = data.get("sip_headers", [])
    sip_headers = {}
    if isinstance(raw_sip_headers, list):
        for h in raw_sip_headers:
            sip_headers[h.get("name", "")] = h.get("value", "")
    elif isinstance(raw_sip_headers, dict):
        sip_headers = raw_sip_headers

    caller_number = sip_headers.get("From", "unknown")

    print(f"\n{'='*60}")
    print(f"[SIP] INCOMING CALL: {call_id}")
    print(f"[SIP] From: {caller_number}")
    print(f"[SIP] SIP Headers: {json.dumps(sip_headers)[:200]}")
    print(f"{'='*60}\n")

    if not call_id:
        print("[SIP] ERROR: No call_id in webhook payload")
        return {"status": "error", "error": "missing call_id"}, 200

    # Accept the call
    try:
        result = await accept_call(call_id, sip_headers)
        # Start monitoring in background (optional)
        asyncio.create_task(monitor_call(call_id))
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

