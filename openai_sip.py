"""
OpenAI SIP Integration - Replaces Twilio for incoming call handling.

Uses OpenAI Realtime API with SIP trunking:
- Webhook-based call routing (incoming calls via POST)
- HMAC-SHA256 signature verification
- Session config with voice model, tools, and MCP servers
- Call lifecycle management (accept, reject, hangup, transfer)

Tool execution:
  Tools are defined as regular OpenAI function-call tools (type="function").
  When the model requests a tool during a call, our WebSocket sideband handler
  intercepts the event, calls the CRM server's /execute REST endpoint, and
  sends the result back — no MCP protocol involved.
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

# CRM function execution endpoint — plain REST, no MCP protocol
CRM_EXECUTE_URL = os.getenv("CRM_EXECUTE_URL", "http://localhost:3100/execute")

# Maximum allowed age for webhook timestamps (5 minutes)
WEBHOOK_TIMESTAMP_TOLERANCE = 300

# ---------------------------------------------------------------------------
# Tool definitions — OpenAI function format (replaces type="mcp")
# Schemas mirror the tool definitions in crm_mcp_server/src/mcp-server.ts
# ---------------------------------------------------------------------------
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "check_customer_history",
        "description": (
            "Check customer history by phone number. "
            "Call IMMEDIATELY when the customer provides their phone number. "
            "Do not respond to the customer until you get the result."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "phone_number": {
                    "type": "string",
                    "description": "Customer phone number (e.g. +14155550123)",
                },
            },
            "required": ["phone_number"],
        },
    },
    {
        "type": "function",
        "name": "add_customer_record",
        "description": "Add a new customer support record to the CRM.",
        "parameters": {
            "type": "object",
            "properties": {
                "make":     {"type": "string", "description": "Vehicle make (e.g. Toyota)"},
                "model":    {"type": "string", "description": "Vehicle model (e.g. Corolla)"},
                "km":       {"type": "string", "description": "Vehicle kilometres"},
                "name":     {"type": "string", "description": "Customer name"},
                "email":    {"type": "string", "description": "Customer email address"},
                "phone":    {"type": "string", "description": "Customer phone number (optional)"},
                "issue":    {"type": "string", "description": "Description of the customer issue"},
                "status":   {
                    "type": "string",
                    "enum": ["open", "in-progress", "resolved", "closed"],
                    "description": "Ticket status",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "urgent"],
                    "description": "Priority level",
                },
                "notes":    {"type": "string", "description": "Additional notes (optional)"},
            },
            "required": ["name", "email", "issue", "status", "priority"],
        },
    },
    {
        "type": "function",
        "name": "get_service_pricing",
        "description": (
            "YOU MUST CALL THIS before quoting ANY price. "
            "Never say a price without calling this first. "
            "Common services: oil change, full service, brake service, tire rotation, "
            "engine diagnostic, transmission service, ac service, battery replacement."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "service_type": {
                    "type": "string",
                    "description": "Type of service (e.g. oil change, brake service)",
                },
                "vehicle_type": {
                    "type": "string",
                    "description": "Type of vehicle: sedan, suv, or truck",
                },
            },
            "required": ["service_type", "vehicle_type"],
        },
    },
    {
        "type": "function",
        "name": "check_availability",
        "description": (
            "YOU MUST CALL THIS before suggesting appointment times. "
            "Do not make up time slots. Customer needs real availability."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "eventTypeUri": {
                    "type": "string",
                    "description": "The Calendly event type URI",
                },
                "startTime": {
                    "type": "string",
                    "description": "Start of search window (ISO 8601, e.g. 2025-12-15T00:00:00Z)",
                },
                "endTime": {
                    "type": "string",
                    "description": "End of search window (ISO 8601, e.g. 2025-12-22T23:59:59Z)",
                },
            },
            "required": ["eventTypeUri", "startTime", "endTime"],
        },
    },
    {
        "type": "function",
        "name": "create_event",
        "description": (
            "Create an appointment booking for a customer with a scheduling link. "
            "Only call this after the customer has explicitly confirmed the appointment."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "eventTypeUri":   {"type": "string", "description": "Calendly event type URI"},
                "customerName":   {"type": "string", "description": "Customer name"},
                "customerEmail":  {"type": "string", "description": "Customer email"},
                "customerPhone":  {"type": "string", "description": "Phone number (optional)"},
                "preferredDate":  {
                    "type": "string",
                    "description": "Preferred ISO datetime (optional, e.g. 2025-12-15T10:00:00Z)",
                },
                "notes":          {"type": "string", "description": "Booking notes (optional)"},
            },
            "required": ["eventTypeUri", "customerName", "customerEmail"],
        },
    },
]

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

    Tools are defined as regular OpenAI function-call tools so that the
    model emits function-call events on the WebSocket sideband.  The
    support_agent then executes them via the CRM server's /execute endpoint
    and returns results — no MCP protocol involved.

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

    session_config = {
        "type": "realtime",
        "model": "gpt-realtime",
        "instructions": instructions,
        "tool_choice": "auto",
        # Regular function tools — handled via WebSocket sideband in support_agent
        "tools": TOOL_DEFINITIONS,
        "audio": {
            "input": {
                "format": "g711_ulaw",
                "turn_detection": {
                    "type": "semantic_vad",
                },
            },
            "output": {"format": "g711_ulaw", "voice": "alloy"},
        },
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


# ---------------------------------------------------------------------------
# 5. CRM function execution via REST
# ---------------------------------------------------------------------------
async def _execute_crm_function(name: str, arguments: dict) -> str:
    """Execute a CRM tool function by calling the /execute REST endpoint.

    This replaces the MCP protocol — the CRM server exposes the same tool
    logic at POST /execute without any MCP framing.

    Args:
        name: Tool name (e.g. "check_customer_history").
        arguments: Tool arguments dict parsed from the model's JSON output.

    Returns:
        Plain-text result string to send back to the model.
    """
    print(f"[CRM] Calling /execute: tool={name} args={json.dumps(arguments)[:200]}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                CRM_EXECUTE_URL,
                json={"name": name, "arguments": arguments},
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = data.get("result", str(data))
                    print(f"[CRM] /execute result ({len(result)} chars): {result[:200]}")
                    return result
                else:
                    text = await resp.text()
                    print(f"[CRM] /execute error {resp.status}: {text[:300]}")
                    return f"Error calling {name}: HTTP {resp.status} — {text[:200]}"
    except Exception as exc:
        print(f"[CRM] /execute exception: {exc}")
        return f"Error calling {name}: {exc}"


# ---------------------------------------------------------------------------
# 6. WebSocket sideband — function call handler
# ---------------------------------------------------------------------------
async def handle_call_websocket(call_id: str) -> None:
    """Connect to the OpenAI Realtime WebSocket sideband for a SIP call and
    handle all function-call events produced by the model.

    Flow for each function call:
      1. Model emits ``response.function_call_arguments.done``
      2. We call the CRM /execute endpoint with the tool name + parsed args
      3. We send ``conversation.item.create`` with the function output
      4. We send ``response.create`` to resume model generation

    Args:
        call_id: The SIP call ID returned by the webhook payload.
    """
    ws_url = f"wss://api.openai.com/v1/realtime?call_id={call_id}"
    print(f"[WS] Connecting sideband for call {call_id}")

    try:
        async with websockets.connect(
            ws_url,
            additional_headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        ) as ws:
            print(f"[WS] Sideband connected for call {call_id}")

            # Buffer for streaming function-call arguments keyed by call_id
            _pending: dict[str, dict] = {}

            async for raw_message in ws:
                try:
                    event = json.loads(raw_message)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")

                # ── Track new function-call output items ──────────────────
                if event_type == "response.output_item.added":
                    item = event.get("item", {})
                    if item.get("type") == "function_call":
                        fn_call_id = item.get("call_id", "")
                        _pending[fn_call_id] = {
                            "name": item.get("name", ""),
                            "arguments": item.get("arguments", ""),
                        }
                        print(f"[WS] Function call started: {item.get('name')} (call_id={fn_call_id})")

                # ── Accumulate streaming argument deltas ──────────────────
                elif event_type == "response.function_call_arguments.delta":
                    fn_call_id = event.get("call_id", "")
                    if fn_call_id in _pending:
                        _pending[fn_call_id]["arguments"] += event.get("delta", "")

                # ── All arguments received — execute the function ─────────
                elif event_type == "response.function_call_arguments.done":
                    fn_call_id = event.get("call_id", "")
                    fn_name = event.get("name", "") or _pending.get(fn_call_id, {}).get("name", "")
                    fn_args_str = event.get("arguments", "") or _pending.get(fn_call_id, {}).get("arguments", "{}")

                    print(f"[WS] Function call complete: {fn_name}({fn_args_str[:200]})")

                    # Parse arguments
                    try:
                        fn_args = json.loads(fn_args_str) if fn_args_str else {}
                    except json.JSONDecodeError as exc:
                        print(f"[WS] Failed to parse arguments for {fn_name}: {exc}")
                        fn_args = {}

                    # Execute via CRM REST endpoint
                    result_text = await _execute_crm_function(fn_name, fn_args)

                    # Send function output back to model
                    await ws.send(json.dumps({
                        "type": "conversation.item.create",
                        "item": {
                            "type": "function_call_output",
                            "call_id": fn_call_id,
                            "output": result_text,
                        },
                    }))

                    # Resume model generation
                    await ws.send(json.dumps({"type": "response.create"}))

                    # Clean up buffer
                    _pending.pop(fn_call_id, None)

                # ── Logging helpers ───────────────────────────────────────
                elif event_type == "response.done":
                    output = event.get("response", {}).get("output", [])
                    has_tool = any(i.get("type") == "function_call" for i in output)
                    if not has_tool:
                        print(f"[WS][{call_id}] Response done (no tool calls)")

                elif event_type.startswith("error"):
                    print(f"[WS][{call_id}] Error event: {json.dumps(event)[:300]}")

    except websockets.exceptions.ConnectionClosedOK:
        print(f"[WS] Sideband closed normally for call {call_id}")
    except Exception as exc:
        print(f"[WS] Sideband error for call {call_id}: {exc}")
        import traceback
        traceback.print_exc()


# ---------------------------------------------------------------------------
# 7. reject_call
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
# 8. hangup_call
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
# 9. transfer_call
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
# 10. create_call_record / destroy_call_record
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

    Extracts call metadata, accepts the call, then launches the WebSocket
    sideband handler as a background task.  The sideband intercepts all
    function-call events produced by the model and executes them via the
    CRM server's /execute endpoint.

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
        # Start WebSocket sideband in background to handle function calls
        asyncio.create_task(handle_call_websocket(call_id))
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
