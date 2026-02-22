"""
Workflow Client - Assistants API Integration

Works with Twilio Native architecture:
- Receives text from Twilio STT
- Processes with OpenAI Assistants API
- Executes CRM tools via the /execute REST endpoint (no MCP protocol)
- Returns text for Twilio TTS

NO audio handling - pure text processing
"""

from agents import Agent, Runner, SQLiteSession, function_tool
import os
import asyncio
import aiohttp
import json as _json

# ---------------------------------------------------------------------------
# CRM Server Configuration
# ---------------------------------------------------------------------------
# Direct function-execution endpoint — no MCP JSON-RPC protocol.
CRM_EXECUTE_URL = os.getenv("CRM_EXECUTE_URL", "http://localhost:3100/execute")


async def _call_crm_tool(tool_name: str, arguments: dict) -> str:
    """Execute a CRM tool function via the /execute REST endpoint.

    Replaces the previous MCP JSON-RPC approach.
    The CRM server exposes the same tool logic at POST /execute without
    any MCP session management or protocol framing.

    Args:
        tool_name: Name of the CRM tool to invoke.
        arguments: Arguments dict to pass to the tool.

    Returns:
        Plain-text result string from the tool.
    """
    print(f"[CRM_CALL] → {tool_name} | URL: {CRM_EXECUTE_URL}")
    print(f"[CRM_CALL] → Args: {_json.dumps(arguments, indent=2)}")

    try:
        async with aiohttp.ClientSession() as http:
            async with http.post(
                CRM_EXECUTE_URL,
                json={"name": tool_name, "arguments": arguments},
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                print(f"[CRM_CALL] ← Status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    result = data.get("result", str(data))
                    print(f"[CRM_CALL] ← Result: {result[:300]}")
                    return result
                else:
                    body = await response.text()
                    print(f"[CRM_CALL] ← ERROR {response.status}: {body[:500]}")
                    return f"Error: CRM server returned status {response.status}: {body}"
    except Exception as exc:
        print(f"[CRM_CALL] ← EXCEPTION: {tool_name}: {exc}")
        import traceback
        traceback.print_exc()
        return f"Error calling CRM tool {tool_name}: {exc}"


# ---------------------------------------------------------------------------
# Function Tools — each calls the CRM /execute endpoint directly
# ---------------------------------------------------------------------------

@function_tool
async def check_customer_history(phone_number: str) -> str:
    """Check customer history by phone number. Call this immediately when you get the customer's phone number."""
    return await _call_crm_tool("check_customer_history", {"phone_number": phone_number})


@function_tool
async def add_customer_record(
    make: str,
    model: str,
    kilometers: str,
    name: str,
    email: str,
    phone: str = "",
    issue: str = "New customer inquiry",
    status: str = "open",
    priority: str = "medium",
    notes: str = "",
) -> str:
    """Add a new customer record to the CRM. Use this for new customers after getting their name and email."""
    args: dict = {
        "make": make,
        "model": model,
        "km": kilometers,
        "name": name,
        "email": email,
        "issue": issue,
        "status": status,
        "priority": priority,
        "notes": notes,
    }
    if phone:
        args["phone"] = phone
    if notes:
        args["notes"] = notes
    return await _call_crm_tool("add_customer_record", args)


@function_tool
async def get_service_pricing(service_type: str, vehicle_type: str) -> str:
    """Get pricing for a car service. Never guess prices — always call this tool. Common services: oil change, full service, brake service, tire rotation, engine diagnostic, transmission service, ac service, battery replacement."""
    return await _call_crm_tool("get_service_pricing", {
        "service_type": service_type,
        "vehicle_type": vehicle_type,
    })


@function_tool
async def check_availability(event_type_uri: str, start_time: str = "", end_time: str = "") -> str:
    """Get available appointment time slots for the week containing the reference date. Call when the customer wants to schedule."""
    args: dict = {"eventTypeUri": 'https://api.calendly.com/event_types/3b49691f-afd5-4c92-8042-e39ad9f76827'}
    if start_time:
        args["startTime"] = start_time
    if end_time:
        args["endTime"] = end_time
    return await _call_crm_tool("check_availability", args)


@function_tool
async def create_event(
  eventTypeUri: str,
    customerName: str,
    customerEmail: str,
    customerPhone: str,
    preferredDate: str
) -> str:
    """Create an appointment booking for the customer. Only call this after explicit customer confirmation."""
    args: dict = {
        "eventTypeUri": 'https://api.calendly.com/event_types/3b49691f-afd5-4c92-8042-e39ad9f76827',
        "customerName": customerName,
        "customerEmail": customerEmail,
        "customerPhone": customerPhone,
        "preferredDate": preferredDate
    }

    return await _call_crm_tool("create_event", args)


# ---------------------------------------------------------------------------
# Workflow Client
# ---------------------------------------------------------------------------

class WorkflowClient:
    def __init__(self):
        """
        Initialize Assistants API client with Zapier MCP tools
        """
        
        # Define your agent
        self.agent = Agent(
            name="Elite Auto Service Assistant",
            instructions="""You are Sarah, a friendly customer support agent for Elite Auto Service Center.

PERSONALITY:
- Warm but efficient
- Concise (1-2 sentences when possible)
- Never robotic or overly formal
- Keep conversations focused and helpful

# YOUR ROLE
Help customers schedule appointments and resolve issues efficiently over the phone.

# CRITICAL PHONE RULES
- Maximum 20 words per response
- ONE question at a time
- Natural conversational speech
- No formatting, bullets, or lists or emojis

# CONVERSATION FLOW

1. GREETING (if first message)
   - Already done by system
   - Just respond to what customer said

2. GET PHONE NUMBER
   "What's your phone number?"
   → IMMEDIATELY call check_customer_history tool

3. HANDLE CUSTOMER LOOKUP
   - If found: "Hi [name]! What service do you need?"
   - If not found add customer record: "Collect details (make, model, km, name, email) and call add_customer_record tool"
   → Call add_customer_record tool

4. GET SERVICE DETAILS
   "What service do you need?"
   "What type of vehicle?" (sedan, SUV, truck)
   → Call get_service_pricing tool
   → Quote: "[Service] for [vehicle] is $[price]"

5. SCHEDULE
   "When would you like to come in?"
   -> If they give a date, call check_availability with that date as reference
   -> If they say "this week" or similar, call check_availability with current week as reference and consider start_time as 9 AM of current day and end_time as 6 PM of the last day of the week
   -> If they say "next week" or similar, call check_availability with next week as reference and consider start_time as 9 AM of the first day of the week and end_time as 6 PM of the last day of the week
   → Call check_availability tool
   → Show 2-3 options: "I have 2 PM and 4 PM. Which works?"

6. CONFIRM & BOOK
   Read back: "[Name], [service], [vehicle], [date] at [time], $[price]. Correct?"
   Wait for "yes"
   → Call create_appointment tool
   "All set! You're booked. Confirmation sent."

# TOOL USAGE
- check_customer_history: Call immediately when you get phone number
- add_customer_record: Only for new customers after getting name and email
- get_service_pricing: Never guess prices, always call this
- event_type_available_times: When customer wants to schedule
- create_appointment: Only after explicit confirmation

# CRITICAL RULES
- NEVER make up prices
- NEVER book without confirmation
- ALWAYS keep responses under 20 words
- ONE question per response
- Use natural phone speech""",
            tools=[
                check_customer_history,
                add_customer_record,
                get_service_pricing,
                check_availability,
                create_event,
            ],
            model="gpt-4o-mini"
        )

        # Track sessions per call
        self.sessions = {}  # call_sid → InMemorySession
        print("Workflow Client initialized")
        print("- Architecture: Twilio Native")
        print("- Using: OpenAI Assistants API")
        # Try to load Zapier MCP tools
        # self._load_mcp_tools()

    async def create_thread(self, call_sid: str) -> str:
        """
        Create conversation session for this call

        Args:
            call_sid: Twilio call SID

        Returns:
            session_id (same as call_sid)
        """
        session = SQLiteSession(db_path=":memory:", session_id=call_sid)
        self.sessions[call_sid] = session
        print(f"[{call_sid}] Created session")
        return call_sid

    async def send_message(self, call_sid: str, customer_message: str) -> str:
        """
        Send customer message to Assistants API, get response

        This is where the conversational AI happens:
        - Agent understands intent
        - Agent calls CRM MCP tools (customer lookup, scheduling, email)
        - Agent generates appropriate response

        Args:
            call_sid: Call SID
            customer_message: Customer speech (from Twilio STT)

        Returns:
            Agent response text (for Twilio TTS)
        """
        # Initialize MCP on first message (if enabled)
        if getattr(self, 'mcp_enabled', False) and not hasattr(self, '_mcp_initialized'):
            await self._initialize_mcp()
        
        # Get or create session
        session = self.sessions.get(call_sid)
        
        if not session:
            print(f"[{call_sid}] No session found, creating new one")
            await self.create_thread(call_sid)
            session = self.sessions[call_sid]

        print(f"[{call_sid}] → Agent: {customer_message}")

        try:
            # Run the agent with the message
            # Use asyncio.to_thread for the synchronous Runner.run_sync call
            result = await asyncio.to_thread(
                Runner.run_sync,
                self.agent,
                customer_message,
                session=session
            )

            response_text = result.final_output
            
            # Ensure response is concise for phone
            if len(response_text.split()) > 30:
                # Truncate if too long
                words = response_text.split()
                response_text = ' '.join(words[:30]) + '...'
            
            print(f"[{call_sid}] ← Agent: {response_text}")

            return response_text

        except Exception as e:
            print(f"[{call_sid}] Error in Assistants API: {e}")
            import traceback
            traceback.print_exc()
            
            # Return friendly fallback
            return "I'm having trouble processing that. Could you repeat?"

    def cleanup(self, call_sid: str):
        """Clean up session after call ends"""
        if call_sid in self.sessions:
            del self.sessions[call_sid]
            print(f"[{call_sid}] Session cleaned up")

    def get_active_sessions(self) -> int:
        """Get count of active sessions"""
        return len(self.sessions)