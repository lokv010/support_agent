"""
CRM Tool Implementations for support_agent

Native Python implementations ported from crm_mcp_server/src/mcp-server.ts.
No HTTP calls to a separate server — all logic runs in-process.

Tools exposed:
  - check_customer_history(phone_number)        → Google Sheets lookup
  - add_customer_record(name, email, ...)        → Google Sheets append
  - get_service_pricing(service_type, vehicle)   → static price table
  - check_availability(eventTypeUri, start, end) → Calendly API
  - create_event(eventTypeUri, name, email, ...) → Calendly scheduling link
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode
from typing import Optional

import aiohttp
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration — read from environment (same vars as crm_mcp_server)
# ---------------------------------------------------------------------------
GOOGLE_SHEETS_CREDENTIALS_PATH = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", "")
GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
CALENDLY_API_TOKEN = os.getenv("CALENDLY_API_TOKEN", "")
CALENDLY_ORGANIZATION_URI = os.getenv("CALENDLY_ORGANIZATION_URI", "")

# Sheet layout — must match headers in the Google Sheet
SHEET_NAME = "CustomerRecords"
HEADERS = [
    "ID", "Make", "Model", "KM", "Name", "Email", "Phone",
    "Issue", "Status", "Priority", "Created At", "Updated At", "Notes",
]
# Column index constants (0-based)
COL_ID, COL_MAKE, COL_MODEL, COL_KM = 0, 1, 2, 3
COL_NAME, COL_EMAIL, COL_PHONE = 4, 5, 6
COL_ISSUE, COL_STATUS, COL_PRIORITY = 7, 8, 9
COL_CREATED, COL_UPDATED, COL_NOTES = 10, 11, 12

# ---------------------------------------------------------------------------
# Service Pricing — static table (mirrors TypeScript SERVICE_PRICING)
# ---------------------------------------------------------------------------
SERVICE_PRICING: dict[str, dict[str, int]] = {
    "oil change":            {"sedan": 49,  "suv": 59,  "truck": 69},
    "full service":          {"sedan": 199, "suv": 249, "truck": 299},
    "brake service":         {"sedan": 149, "suv": 179, "truck": 209},
    "tire rotation":         {"sedan": 39,  "suv": 49,  "truck": 55},
    "engine diagnostic":     {"sedan": 89,  "suv": 89,  "truck": 99},
    "transmission service":  {"sedan": 179, "suv": 219, "truck": 259},
    "ac service":            {"sedan": 129, "suv": 149, "truck": 159},
    "battery replacement":   {"sedan": 159, "suv": 169, "truck": 189},
    "wheel alignment":       {"sedan": 89,  "suv": 99,  "truck": 109},
    "coolant flush":         {"sedan": 99,  "suv": 119, "truck": 139},
}

# ---------------------------------------------------------------------------
# Google Sheets — lazy-initialised service client
# ---------------------------------------------------------------------------
_sheets_service = None


def _get_sheets_service():
    """Return a cached Google Sheets v4 service, initialising on first call."""
    global _sheets_service
    if _sheets_service is not None:
        return _sheets_service

    if not GOOGLE_SHEETS_CREDENTIALS_PATH:
        raise RuntimeError(
            "GOOGLE_SHEETS_CREDENTIALS_PATH is not set. "
            "Point it to your service-account JSON file."
        )
    if not GOOGLE_SHEETS_SPREADSHEET_ID:
        raise RuntimeError("GOOGLE_SHEETS_SPREADSHEET_ID is not set.")

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_SHEETS_CREDENTIALS_PATH,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    _sheets_service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    print("[CRM] Google Sheets service initialised")
    return _sheets_service


def _col_letter(n: int) -> str:
    """Convert 1-based column index to spreadsheet letter (1→A, 27→AA)."""
    s = ""
    while n > 0:
        rem = (n - 1) % 26
        s = chr(65 + rem) + s
        n = (n - 1) // 26
    return s


def _row_to_record(row: list) -> dict:
    """Pad a sheet row to full width and return a named dict."""
    row = list(row) + [""] * (len(HEADERS) - len(row))
    return {
        "id":         row[COL_ID],
        "make":       row[COL_MAKE],
        "model":      row[COL_MODEL],
        "km":         row[COL_KM],
        "name":       row[COL_NAME],
        "email":      row[COL_EMAIL],
        "phone":      row[COL_PHONE],
        "issue":      row[COL_ISSUE],
        "status":     row[COL_STATUS],
        "priority":   row[COL_PRIORITY],
        "created_at": row[COL_CREATED],
        "updated_at": row[COL_UPDATED],
        "notes":      row[COL_NOTES],
    }


def _sheets_fetch_all_rows() -> list[list]:
    """Blocking call — fetch every row from the CustomerRecords sheet."""
    svc = _get_sheets_service()
    end_col = _col_letter(len(HEADERS))
    result = (
        svc.spreadsheets()
        .values()
        .get(
            spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A:{end_col}",
        )
        .execute()
    )
    return result.get("values", [])


def _sheets_append_row(row: list) -> None:
    """Blocking call — append one row to the CustomerRecords sheet."""
    svc = _get_sheets_service()
    end_col = _col_letter(len(HEADERS))
    (
        svc.spreadsheets()
        .values()
        .append(
            spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A1:{end_col}",
            valueInputOption="RAW",
            body={"values": [row]},
        )
        .execute()
    )


# ---------------------------------------------------------------------------
# Tool: check_customer_history
# ---------------------------------------------------------------------------
async def check_customer_history(phone_number: str) -> str:
    """Look up a customer by phone number in the Google Sheet.

    Args:
        phone_number: E.164 or local phone number string.

    Returns:
        JSON string with found count and list of matching customer records.
    """
    print(f"[CRM] check_customer_history: phone={phone_number}")
    loop = asyncio.get_event_loop()

    try:
        rows = await loop.run_in_executor(None, _sheets_fetch_all_rows)
    except Exception as exc:
        print(f"[CRM] check_customer_history error: {exc}")
        return json.dumps({"error": f"Failed to access customer records: {exc}"})

    # Row 0 is the header — Phone is at COL_PHONE (index 6)
    matching = [
        _row_to_record(row)
        for row in rows[1:]
        if len(row) > COL_PHONE and row[COL_PHONE] == phone_number
    ]

    print(f"[CRM] check_customer_history: found {len(matching)} record(s) for {phone_number}")
    return json.dumps(
        {
            "found": len(matching),
            "phone_number": phone_number,
            "records": matching,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool: add_customer_record
# ---------------------------------------------------------------------------
async def add_customer_record(
    name: str,
    email: str,
    issue: str,
    status: str,
    priority: str,
    make: str = "",
    model: str = "",
    km: str = "",
    phone: str = "",
    notes: str = "",
) -> str:
    """Append a new customer record to the Google Sheet.

    Args:
        name:     Customer full name.
        email:    Customer email address.
        issue:    Description of the service issue.
        status:   Ticket status (open | in-progress | resolved | closed).
        priority: Priority level (low | medium | high | urgent).
        make:     Vehicle make (e.g. Toyota). Optional.
        model:    Vehicle model (e.g. Corolla). Optional.
        km:       Vehicle kilometres. Optional.
        phone:    Customer phone number. Optional.
        notes:    Additional notes. Optional.

    Returns:
        JSON string with success status and new record ID.
    """
    print(f"[CRM] add_customer_record: name={name}, email={email}")
    loop = asyncio.get_event_loop()

    record_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    # Order must match HEADERS exactly
    row = [
        record_id, make, model, km,
        name, email, phone,
        issue, status, priority,
        timestamp, timestamp, notes,
    ]

    try:
        await loop.run_in_executor(None, _sheets_append_row, row)
    except Exception as exc:
        print(f"[CRM] add_customer_record error: {exc}")
        return json.dumps({"error": f"Failed to add customer record: {exc}"})

    print(f"[CRM] add_customer_record: created ID={record_id}")
    return json.dumps(
        {
            "success": True,
            "id": record_id,
            "message": f"Customer record created successfully with ID: {record_id}",
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool: get_service_pricing
# ---------------------------------------------------------------------------
async def get_service_pricing(service_type: str, vehicle_type: str) -> str:
    """Return the price for a service/vehicle combination from the static table.

    Args:
        service_type: e.g. "oil change", "brake service", "full service".
        vehicle_type: "sedan", "suv", or "truck".

    Returns:
        JSON string with price and currency, or an error with available options.
    """
    print(f'[CRM] get_service_pricing: service="{service_type}", vehicle="{vehicle_type}"')

    svc_key = service_type.lower().strip()
    veh_key = vehicle_type.lower().strip()

    service_prices = SERVICE_PRICING.get(svc_key)
    if service_prices is None:
        return json.dumps(
            {
                "error": f'Unknown service type: "{service_type}"',
                "available_services": list(SERVICE_PRICING.keys()),
            },
            indent=2,
        )

    price = service_prices.get(veh_key)
    if price is None:
        return json.dumps(
            {
                "error": f'Unknown vehicle type: "{vehicle_type}"',
                "available_vehicle_types": list(service_prices.keys()),
            },
            indent=2,
        )

    return json.dumps(
        {
            "service_type": service_type,
            "vehicle_type": vehicle_type,
            "price": price,
            "currency": "USD",
            "formatted_price": f"${price}",
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Calendly helper
# ---------------------------------------------------------------------------
async def _calendly_request(
    path: str,
    method: str = "GET",
    body: Optional[dict] = None,
) -> dict:
    """Authenticated Calendly API request.

    Args:
        path:   URL path starting with "/" (e.g. "/event_types").
        method: HTTP method (default GET).
        body:   JSON payload for POST requests.

    Returns:
        Parsed JSON response dict.

    Raises:
        RuntimeError: If CALENDLY_API_TOKEN is not configured or API returns error.
    """
    if not CALENDLY_API_TOKEN:
        raise RuntimeError("CALENDLY_API_TOKEN is not configured")

    url = f"https://api.calendly.com{path}"
    headers = {
        "Authorization": f"Bearer {CALENDLY_API_TOKEN}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as session:
        kwargs: dict = {
            "headers": headers,
            "timeout": aiohttp.ClientTimeout(total=30),
        }
        if body is not None:
            kwargs["json"] = body

        async with session.request(method, url, **kwargs) as resp:
            if not resp.ok:
                text = await resp.text()
                raise RuntimeError(
                    f"Calendly API error {resp.status}: {text[:300]}"
                )
            return await resp.json()


# ---------------------------------------------------------------------------
# Tool: check_availability
# ---------------------------------------------------------------------------
async def check_availability(
    eventTypeUri: str,
    startTime: str,
    endTime: str,
) -> str:
    """Return available Calendly time slots in the given window.

    Args:
        eventTypeUri: Full Calendly event type URI.
        startTime:    Window start in ISO 8601 (e.g. "2025-12-15T00:00:00Z").
        endTime:      Window end in ISO 8601 (e.g.  "2025-12-21T23:59:59Z").

    Returns:
        JSON string listing available slots, or a message if none found.
    """
    print(f"[CRM] check_availability: {eventTypeUri} [{startTime} → {endTime}]")

    params = urlencode({
        "event_type": eventTypeUri,
        "start_time": startTime,
        "end_time":   endTime,
    })

    try:
        data = await _calendly_request(f"/event_type_available_times?{params}")
    except Exception as exc:
        print(f"[CRM] check_availability error: {exc}")
        return json.dumps({"error": f"Failed to check availability: {exc}"})

    collection = data.get("collection", [])
    if not collection:
        return json.dumps(
            {
                "available_slots": [],
                "message": f"No available time slots between {startTime} and {endTime}",
            },
            indent=2,
        )

    slots = [
        {
            "start_time":          slot.get("start_time"),
            "status":              slot.get("status"),
            "invitees_remaining":  slot.get("invitees_remaining"),
        }
        for slot in collection
    ]

    return json.dumps(
        {
            "event_type":    eventTypeUri,
            "search_period": {"start": startTime, "end": endTime},
            "total_slots":   len(slots),
            "available_times": slots,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool: create_event
# ---------------------------------------------------------------------------
async def create_event(
    eventTypeUri: str,
    customerName: str,
    customerEmail: str,
    customerPhone: str = "",
    preferredDate: str = "",
    notes: str = "",
) -> str:
    """Create a single-use Calendly scheduling link for a customer.

    Mirrors the TypeScript createEvent() function exactly.

    Args:
        eventTypeUri:  Full Calendly event type URI.
        customerName:  Customer full name.
        customerEmail: Customer email address.
        customerPhone: Customer phone number (optional).
        preferredDate: ISO 8601 datetime to pre-select (optional).
        notes:         Booking notes (optional).

    Returns:
        JSON string with booking URL, event details, and workflow guidance.
    """
    print(
        f"[CRM] create_event: {customerName} <{customerEmail}>, "
        f"date={preferredDate or 'any'}"
    )

    try:
        # Step 1 — Fetch event type details
        event_type_id = eventTypeUri.split("/")[-1]
        event_type_data = await _calendly_request(f"/event_types/{event_type_id}")
        event_type = event_type_data.get("resource", {})

        # Step 2 — Create single-use scheduling link
        link_payload: dict = {
            "max_event_count": 1,
            "owner":           eventTypeUri,
            "owner_type":      "EventType",
        }
        if preferredDate:
            date_only = preferredDate[:10]  # "YYYY-MM-DD"
            link_payload["date_setting"] = {
                "type":       "date_range",
                "start_date": date_only,
                "end_date":   date_only,
            }

        link_response = await _calendly_request(
            "/scheduling_links", method="POST", body=link_payload
        )
        booking_url = link_response["resource"]["booking_url"]

        # Step 3 — Build pre-filled URL
        params: dict = {"name": customerName, "email": customerEmail}
        if customerPhone:
            params["a1"] = customerPhone
        if notes:
            params["a2"] = notes
        if preferredDate:
            params["date"] = preferredDate[:10]
            if "T" in preferredDate:
                time_part = preferredDate.split("T")[1][:5]  # "HH:MM"
                params["time"] = time_part

        prefilled_url = f"{booking_url}?{urlencode(params)}"

        # Step 4 — Optionally check availability for the preferred date
        availability_info: Optional[dict] = None
        if preferredDate:
            try:
                date_start = preferredDate[:10] + "T00:00:00Z"
                date_end   = preferredDate[:10] + "T23:59:59Z"
                avail_params = urlencode({
                    "event_type": eventTypeUri,
                    "start_time": date_start,
                    "end_time":   date_end,
                })
                avail_data = await _calendly_request(
                    f"/event_type_available_times?{avail_params}"
                )
                avail_collection = avail_data.get("collection", [])
                if avail_collection:
                    exact_slot = next(
                        (
                            s for s in avail_collection
                            if s.get("start_time", "") == preferredDate
                        ),
                        None,
                    )
                    availability_info = {
                        "requested_time":      preferredDate,
                        "exact_slot_available": exact_slot is not None,
                        "total_slots_on_date": len(avail_collection),
                        "nearest_slots": [
                            {
                                "start_time":         s.get("start_time"),
                                "status":             s.get("status"),
                                "invitees_remaining": s.get("invitees_remaining"),
                            }
                            for s in avail_collection[:3]
                        ],
                    }
                else:
                    availability_info = {
                        "requested_time":      preferredDate,
                        "exact_slot_available": False,
                        "total_slots_on_date": 0,
                        "message": "No availability on requested date",
                    }
            except Exception as avail_exc:
                availability_info = {
                    "requested_time": preferredDate,
                    "error": f"Could not check availability: {avail_exc}",
                }

        # Step 5 — Build response
        result: dict = {
            "success":          True,
            "message": (
                "Scheduling link created with preferred date/time pre-selected"
                if preferredDate
                else "Scheduling link generated — customer can select any available time"
            ),
            "booking_url":       prefilled_url,
            "booking_url_short": booking_url,
            "expires_after":     "1 booking",
            "event_details": {
                "name":        event_type.get("name"),
                "duration":    f"{event_type.get('duration')} minutes",
                "description": event_type.get("description_plain") or "No description",
                "type":        event_type.get("type"),
            },
            "customer": {
                "name":  customerName,
                "email": customerEmail,
                "phone": customerPhone or "Not provided",
                "notes": notes or "None",
            },
        }

        if preferredDate:
            result["preferred_datetime"] = {
                "requested": preferredDate,
                "date":      preferredDate[:10],
                "time":      preferredDate.split("T")[1][:5] if "T" in preferredDate else "",
                "timezone":  "UTC",
            }

        if availability_info:
            result["availability"] = availability_info

        result["workflow"] = (
            {
                "current_step": "Link generated with pre-selected date/time",
                "status":       "Awaiting customer confirmation",
                "next_steps": [
                    "1. Share the booking_url with the customer",
                    "2. Customer reviews pre-selected date/time",
                    "3. Customer confirms or selects alternative",
                    "4. Booking confirmed automatically",
                    "5. Both parties receive confirmation email",
                ],
            }
            if preferredDate
            else {
                "current_step": "Link generated",
                "status":       "Awaiting customer to select time",
                "next_steps": [
                    "1. Share the booking_url with the customer",
                    "2. Customer selects preferred time",
                    "3. Customer confirms booking",
                    "4. Both parties receive confirmation email",
                ],
            }
        )

        return json.dumps(result, indent=2)

    except Exception as exc:
        print(f"[CRM] create_event error: {exc}")
        import traceback
        traceback.print_exc()
        return json.dumps({"error": f"Failed to create event: {exc}"})


# ---------------------------------------------------------------------------
# Dispatch helper — used by openai_sip.py WebSocket sideband
# ---------------------------------------------------------------------------
_TOOL_MAP = {
    "check_customer_history": check_customer_history,
    "add_customer_record":    add_customer_record,
    "get_service_pricing":    get_service_pricing,
    "check_availability":     check_availability,
    "create_event":           create_event,
}


async def dispatch(tool_name: str, arguments: dict) -> str:
    """Execute a named CRM tool with the given arguments.

    Used by the WebSocket sideband handler in openai_sip.py so that
    tool dispatch is a single function call with no HTTP round-trip.

    Args:
        tool_name:  One of the five supported tool names.
        arguments:  Dict of keyword arguments for the tool function.

    Returns:
        Plain-text / JSON result string.
    """
    fn = _TOOL_MAP.get(tool_name)
    if fn is None:
        known = ", ".join(_TOOL_MAP.keys())
        return json.dumps({"error": f"Unknown tool '{tool_name}'. Known tools: {known}"})

    try:
        return await fn(**arguments)
    except TypeError as exc:
        # Missing / unexpected argument
        return json.dumps({"error": f"Invalid arguments for {tool_name}: {exc}"})
    except Exception as exc:
        return json.dumps({"error": f"Tool {tool_name} raised an exception: {exc}"})
