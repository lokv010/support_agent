"""
Agent Integration using OpenAI Agents SDK + CRM MCP Server

This is the BRAIN of the system.
Agent with instructions and MCP tools from the CRM MCP Server.
"""

from agents import Agent, Runner, SQLiteSession
from agents.mcp import MCPServerStreamableHttp
import os
import asyncio


CRM_MCP_URL = os.getenv("CRM_MCP_URL", "http://localhost:3100/mcp")


class WorkflowClient:
    def __init__(self):
        self.crm_server = MCPServerStreamableHttp(
            name="CRM MCP Server",
            params={
                "url": CRM_MCP_URL,
                "timeout": 30,
            },
            cache_tools_list=True,
        )

        self.agent = Agent(
            name="Support Assistant",
            instructions="""You are a helpful customer support assistant for an automotive service center.

Your role is to:
- Greet customers warmly
- Answer their questions about services
- Help with scheduling appointments using Calendly tools
- Look up customer records and history using CRM tools
- Create and update customer records as needed
- Send confirmation emails after booking appointments
- Handle requests professionally

When a customer calls:
1. Check if they are an existing customer using check_customer_history with their phone number
2. If they want to schedule, use list_event_types to show available appointment types
3. Use event_type_available_times to check availability
4. Use create_event to create a booking link
5. After booking, use add_customer_record or update_customer_record to log the interaction
6. Use send_appointment_confirmation to email the customer

Keep responses concise and conversational since this is a voice call.
""",
            mcp_servers=[self.crm_server],
        )

        # Track sessions per call
        self.sessions = {}  # call_sid -> InMemorySession
        self._connected = False

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
        if not self._connected:
            await self.connect()

        session = SQLiteSession(db_path=":memory:", session_id=call_sid)
        self.sessions[call_sid] = session
        print(f"[{call_sid}] Created session")
        return call_sid

    async def send_message(self, call_sid: str, text: str) -> str:
        """
        Send message to Agent, get response

        This is where ALL the magic happens:
        - Agent understands intent
        - Agent calls CRM MCP tools (customer lookup, scheduling, email)
        - Agent generates response

        Args:
            call_sid: Call SID
            text: Customer message (from STT)

        Returns:
            Agent response text (for TTS)
        """
        session = self.sessions.get(call_sid)

        if not session:
            await self.create_thread(call_sid)
            session = self.sessions[call_sid]

        print(f"[{call_sid}] -> Agent: {text}")

        result = await Runner.run(
            self.agent,
            text,
            session=session
        )

        response_text = result.final_output
        print(f"[{call_sid}] <- Agent: {response_text}")

        return response_text

    def cleanup(self, call_sid: str):
        """Clean up session"""
        if call_sid in self.sessions:
            del self.sessions[call_sid]
            print(f"[{call_sid}] Session cleaned up")
