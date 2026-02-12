"""
Workflow Client - Assistants API Integration

Works with Twilio Native architecture:
- Receives text from Twilio STT
- Processes with OpenAI Assistants API
- Can use Zapier MCP tools
- Returns text for Twilio TTS

NO audio handling - pure text processing
"""

from agents import Agent, Runner, SQLiteSession
import os
import asyncio
import aiohttp
from mcp import ClientSession
from mcp.client.sse import sse_client
from openai import http_client
from agents import Agent, Runner, SQLiteSession
from agents.mcp import MCPServerStreamableHttp

CRM_MCP_URL = os.getenv("CRM_MCP_URL", "http://localhost:3100/mcp")

class WorkflowClient:
    def __init__(self):
        """
        Initialize Assistants API client with Zapier MCP tools
        """
        self.crm_server = MCPServerStreamableHttp(
            name="CRM MCP Server",
            params={
                "url": CRM_MCP_URL,
                "timeout": 30,
            },
            cache_tools_list=True,
        )
       
        
        # Define your agent
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
            # Tools will be added here if Zapier MCP is connected
            # For now, agent works without tools for testing
            tools=[],
            model="gpt-3.5-turbo"
        )

        # Track sessions per call
        self.sessions = {}  # call_sid → InMemorySession
        self._connected = False

        print("Workflow Client initialized")
        print("- Architecture: Twilio Native")
        print("- Using: OpenAI Assistants API")
        # Try to load Zapier MCP tools
        # self._load_mcp_tools()

    async def connect(self):
        """Connect to the CRM MCP server."""
        if not self._connected:
            await self.crm_server.__aenter__()
            self._connected = True
            print(f"[WorkflowClient] Connected to CRM MCP at {CRM_MCP_URL}")

    async def disconnect(self):
        """Disconnect from the CRM MCP server."""
        if self._connected:
            await self.crm_server.__aexit__(None, None, None)
            self._connected = False
            print("[WorkflowClient] Disconnected from CRM MCP")


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