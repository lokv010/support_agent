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
from urllib.parse import urlencode, quote
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
GOOGLE_CALENDAR_ID= os.getenv("GOOGLE_CALENDAR_ID")
GOOGLE_CALENDAR_CREDENTIALS_PATH = os.getenv('GOOGLE_CALENDAR_CREDENTIALS_PATH')
SHOP_TIMEZONE = os.getenv('SHOP_TIMEZONE', 'America/Toronto')
SCOPES_FOR_ACL_MANAGEMENT = 'https://www.googleapis.com/auth/calendar'



# Shop hours
SHOP_HOURS = {
    'monday': {'start': '08:00', 'end': '18:00'},
    'tuesday': {'start': '08:00', 'end': '18:00'},
    'wednesday': {'start': '08:00', 'end': '18:00'},
    'thursday': {'start': '08:00', 'end': '18:00'},
    'friday': {'start': '08:00', 'end': '18:00'},
    'saturday': {'start': '09:00', 'end': '16:00'},
    'sunday': None,  # Closed
}

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
    """Look up a customer by phone number in the Google Sheet."""
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
    """Append a new customer record to the Google Sheet."""
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
    """Return the price for a service/vehicle combination from the static table. """
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

"""
Google Calendar Tools for Auto Shop Appointments
"""

import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pytz



# Appointment durations (in minutes)
SERVICE_DURATIONS = {
    'oil_change': 30,
    'brake_service': 60,
    'tire_rotation': 30,
    'inspection': 45,
    'engine_diagnostic': 90,
    'transmission_service': 120,
    'ac_service': 60,
    'battery_replacement': 20,
}

# Shop hours
SHOP_HOURS = {
    'monday': {'start': '08:00', 'end': '18:00'},
    'tuesday': {'start': '08:00', 'end': '18:00'},
    'wednesday': {'start': '08:00', 'end': '18:00'},
    'thursday': {'start': '08:00', 'end': '18:00'},
    'friday': {'start': '08:00', 'end': '18:00'},
    'saturday': {'start': '09:00', 'end': '16:00'},
    'sunday': None,  # Closed
}


def get_calendar_service():
    """Initialize Google Calendar API client"""
    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_CALENDAR_CREDENTIALS_PATH,
        scopes=['https://www.googleapis.com/auth/calendar']
    )
    return build('calendar', 'v3', credentials=credentials)


async def check_available_schedule(
    service_type: str,
    start_date: Optional[str] = None,
    days_ahead: int = 7
) -> str:
    try:
        service = get_calendar_service()
        tz = pytz.timezone(SHOP_TIMEZONE)
        
        # Parse start date or use tomorrow
        if start_date:
            search_start = datetime.fromisoformat(start_date).astimezone(tz)
        else:
            search_start = (datetime.now(tz) + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        
        search_end = search_start + timedelta(days=days_ahead)
        
        # Get duration for service
        duration_minutes = SERVICE_DURATIONS.get(service_type, 60)
        
        # Fetch existing events in time range
        events_result = service.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=search_start.isoformat(),
            timeMax=search_end.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        existing_events = events_result.get('items', [])
        
        # Generate available slots
        available_slots = []
        current_date = search_start
        
        while current_date < search_end:
            day_name = current_date.strftime('%A').lower()
            
            # Check if shop is open this day
            if SHOP_HOURS.get(day_name) is None:
                current_date += timedelta(days=1)
                continue
            
            shop_day = SHOP_HOURS[day_name]
            
            # Parse shop hours for this day
            start_hour, start_min = map(int, shop_day['start'].split(':'))
            end_hour, end_min = map(int, shop_day['end'].split(':'))
            
            day_start = current_date.replace(hour=start_hour, minute=start_min)
            day_end = current_date.replace(hour=end_hour, minute=end_min)
            
            # Generate 30-minute intervals
            slot_start = day_start
            while slot_start + timedelta(minutes=duration_minutes) <= day_end:
                slot_end = slot_start + timedelta(minutes=duration_minutes)
                
                # Check if slot conflicts with existing event
                is_available = True
                for event in existing_events:
                    event_start = datetime.fromisoformat(
                        event['start'].get('dateTime', event['start'].get('date'))
                    )
                    event_end = datetime.fromisoformat(
                        event['end'].get('dateTime', event['end'].get('date'))
                    )
                    
                    # Check overlap
                    if not (slot_end <= event_start or slot_start >= event_end):
                        is_available = False
                        break
                
                if is_available and slot_start > datetime.now(tz):
                    available_slots.append({
                        'datetime': slot_start.isoformat(),
                        'day': slot_start.strftime('%A'),
                        'date': slot_start.strftime('%B %d, %Y'),
                        'time': slot_start.strftime('%I:%M %p')
                    })
                
                slot_start += timedelta(minutes=30)  # 30-min intervals
            
            current_date += timedelta(days=1)

        return json.dumps({
            'available_slots': available_slots[:20],  # Limit to 20 slots
            'service_type': service_type,
            'duration_minutes': duration_minutes,
            'total_slots_found': len(available_slots)
        })
        
    except Exception as e:
        return json.dumps({
            'error': str(e),
            'available_slots': []
        })


async def book_meeting(
    customer_name: str,
    customer_email: str,
    customer_phone: str,
    service_type: str,
    appointment_datetime: str,
    vehicle_info: Optional[str] = None
) -> str:
    try:
        service = get_calendar_service()
        tz = pytz.timezone(SHOP_TIMEZONE)
        
        # Parse appointment time
        start_time = datetime.fromisoformat(appointment_datetime).astimezone(tz)
        
        # Calculate end time based on service duration
        service_key = service_type.replace(' ', '_').lower()
        duration_minutes = SERVICE_DURATIONS.get(service_key, 60)
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        # Create event
        event = {
            'summary': f'{service_type.replace("_", " ").title()} - {customer_name}',
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': SHOP_TIMEZONE,
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': SHOP_TIMEZONE,
            }
        }
        print(f"[CRM] Booking event for {customer_name} on {start_time.isoformat()} for service {service_type} google calendar id: {GOOGLE_CALENDAR_ID}")
        
        # Insert event
        created_event = service.events().insert(
            calendarId=GOOGLE_CALENDAR_ID,
            body=event
        ).execute()

        return json.dumps(  {
            'success': True,
            'event_id': created_event['id'],
            'event_link': created_event.get('htmlLink'),
            'confirmation': f"Appointment confirmed for {start_time.strftime('%A, %B %d at %I:%M %p')}",
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_minutes': duration_minutes
        })
        
    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e)
        })


async def cancel_appointment(event_id: str, reason: Optional[str] = None) -> Dict:
    """Cancel an existing appointment"""
    try:
        service = get_calendar_service()
        
        # Delete event
        service.events().delete(
            calendarId=GOOGLE_CALENDAR_ID,
            eventId=event_id,
            sendUpdates='all'  # Notify customer
        ).execute()

        return {
            'success': True,
            'message': f'Appointment cancelled{f": {reason}" if reason else ""}'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
# ---------------------------------------------------------------------------
# Dispatch helper — used by openai_sip.py WebSocket sideband
# ---------------------------------------------------------------------------
_TOOL_MAP = {
    "check_customer_history": check_customer_history,
    "add_customer_record":    add_customer_record,
    "get_service_pricing":    get_service_pricing,
    "check_availability":     check_available_schedule,
    "book_meeting":           book_meeting,
}


async def dispatch(tool_name: str, arguments: dict) -> str:
    """Execute a named CRM tool with the given arguments."""
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
