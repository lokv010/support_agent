"""
Workflow Client - Assistants API Integration with CRM MCP Tools

Works with Twilio Native architecture:
- Receives text from Twilio STT
- Processes with OpenAI Assistants API
- Calls CRM MCP server tools (Google Sheets, Calendly, SendGrid)
- Returns text for Twilio TTS

NO audio handling - pure text processing
"""

from agents import Agent, Runner, SQLiteSession, function_tool
import os
import asyncio
import aiohttp

# ---------------------------------------------------------------------------
# MCP Server Configuration
# ---------------------------------------------------------------------------
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:3100/mcp")


async def _mcp_call(tool_name: str, arguments: dict) -> str:
    """Call a CRM MCP server tool via HTTP JSON-RPC."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                MCP_SERVER_URL,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments,
                    },
                },
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    result = data.get("result", {})
                    content = result.get("content", [])
                    if content:
                        return content[0].get("text", str(result))
                    return str(result)
                else:
                    body = await response.text()
                    return f"Error: MCP server returned status {response.status}: {body}"
    except Exception as e:
        return f"Error calling MCP tool {tool_name}: {e}"


# ---------------------------------------------------------------------------
# Function Tools — each wraps an MCP server call
# ---------------------------------------------------------------------------

@function_tool
async def check_customer_history(phone_number: str) -> str:
    """Check customer history by phone number. Call this immediately when you get the customer's phone number."""
    return await _mcp_call("check_customer_history", {"phone_number": phone_number})


@function_tool
async def add_customer_record(
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
        "name": name,
        "email": email,
        "issue": issue,
        "status": status,
        "priority": priority,
    }
    if phone:
        args["phone"] = phone
    if notes:
        args["notes"] = notes
    return await _mcp_call("add_customer_record", args)


@function_tool
async def get_service_pricing(service_type: str, vehicle_type: str) -> str:
    """Get pricing for a car service. Never guess prices — always call this tool. Common services: oil change, full service, brake service, tire rotation, engine diagnostic, transmission service, ac service, battery replacement."""
    return await _mcp_call("get_service_pricing", {
        "service_type": service_type,
        "vehicle_type": vehicle_type,
    })


@function_tool
async def event_type_available_times(event_type_uri: str, reference_date: str = "") -> str:
    """Get available appointment time slots for the week containing the reference date. Call when the customer wants to schedule."""
    args: dict = {"eventTypeUri": event_type_uri}
    if reference_date:
        args["referenceDate"] = reference_date
    return await _mcp_call("event_type_available_times", args)


@function_tool
async def create_appointment(
    event_type_uri: str,
    customer_name: str,
    customer_email: str,
    customer_phone: str = "",
    preferred_date: str = "",
    notes: str = "",
) -> str:
    """Create an appointment booking for the customer. Only call this after explicit customer confirmation."""
    args: dict = {
        "eventTypeUri": event_type_uri,
        "customerName": customer_name,
        "customerEmail": customer_email,
    }
    if customer_phone:
        args["customerPhone"] = customer_phone
    if preferred_date:
        args["preferredDate"] = preferred_date
    if notes:
        args["notes"] = notes
    return await _mcp_call("create_appointment", args)


# ---------------------------------------------------------------------------
# Workflow Client
# ---------------------------------------------------------------------------

class WorkflowClient:
    def __init__(self):
        """Initialize Assistants API client with CRM MCP tools."""

        self.agent = Agent(
            name="Elite Auto Service Assistant",
            instructions="""You are Sarah, a professional phone support agent for Elite Auto Service Center.

# YOUR ROLE
Book car service appointments efficiently over the phone.

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
   - If not found: "What's your name?" then "And your email?"
   → Call add_customer_record tool

4. GET SERVICE DETAILS
   "What service do you need?" (oil change, full service, etc.)
   "What type of vehicle?" (sedan, SUV, truck)
   → Call get_service_pricing tool
   → Quote: "[Service] for [vehicle] is $[price]"

5. SCHEDULE
   "When would you like to come in?"
   → Call event_type_available_times tool
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
                event_type_available_times,
                create_appointment,
            ],
            model="gpt-4o-mini",
        )

        # Track sessions per call
        self.sessions = {}  # call_sid → SQLiteSession

        print("Workflow Client initialized")
        print("- Architecture: Twilio Native")
        print("- Using: OpenAI Assistants API")
        print(f"- CRM MCP Server: {MCP_SERVER_URL}")
        print("- Tools: check_customer_history, add_customer_record, get_service_pricing, event_type_available_times, create_appointment")

    async def create_thread(self, call_sid: str) -> str:
        """
        Create conversation session for this call.

        Args:
            call_sid: Twilio call SID

        Returns:
            session_id (same as call_sid)
        """
        session = SQLiteSession(session_id=call_sid)
        self.sessions[call_sid] = session
        print(f"[{call_sid}] Created session")
        return call_sid

    async def send_message(self, call_sid: str, customer_message: str) -> str:
        """
        Send customer message to Assistants API, get response.

        The agent can autonomously call CRM MCP tools during processing
        (check_customer_history, add_customer_record, get_service_pricing,
        event_type_available_times, create_appointment).

        Args:
            call_sid: Call SID
            customer_message: Customer speech (from Twilio STT)

        Returns:
            Agent response text (for Twilio TTS)
        """
        # Get or create session
        session = self.sessions.get(call_sid)

        if not session:
            print(f"[{call_sid}] No session found, creating new one")
            await self.create_thread(call_sid)
            session = self.sessions[call_sid]

        print(f"[{call_sid}] → Agent: {customer_message}")

        try:
            # Run the agent (async) — it will call MCP tools as needed
            result = await Runner.run(
                self.agent,
                customer_message,
                session=session,
            )

            response_text = result.final_output

            # Ensure response is concise for phone
            if len(response_text.split()) > 30:
                words = response_text.split()
                response_text = " ".join(words[:30]) + "..."

            print(f"[{call_sid}] ← Agent: {response_text}")

            return response_text

        except Exception as e:
            print(f"[{call_sid}] Error in Assistants API: {e}")
            import traceback
            traceback.print_exc()

            return "I'm having trouble processing that. Could you repeat?"

    def cleanup(self, call_sid: str):
        """Clean up session after call ends."""
        if call_sid in self.sessions:
            del self.sessions[call_sid]
            print(f"[{call_sid}] Session cleaned up")

    def get_active_sessions(self) -> int:
        """Get count of active sessions."""
        return len(self.sessions)
