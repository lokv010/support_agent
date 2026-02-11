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


class WorkflowClient:
    def __init__(self):
        """
        Initialize Assistants API client with Zapier MCP tools
        """
        self.mcp_session = None
        self.mcp_tools = []
        
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

        print("Workflow Client initialized")
        print("- Architecture: Twilio Native")
        print("- Using: OpenAI Assistants API")
        # Try to load Zapier MCP tools
        self._load_mcp_tools()

    def _load_mcp_tools(self):
        """
        Load Custom MCP tools from localhost:3100
        This is called synchronously, so we schedule async initialization
        """
        try:
            # Check if custom MCP server is available
            # No secret needed for localhost server
            
            print("- Tools: Custom MCP server at http://localhost:3100/mcp")
            print("- Tools: Will connect on first use")
            self.mcp_enabled = True
            
        except Exception as e:
            print(f"- Tools: Error checking MCP: {e}")
            self.mcp_enabled = False
        
    async def _initialize_mcp(self):
        """
        Initialize MCP connection using HTTP JSON-RPC
        Called once on first message
        """
        if hasattr(self, '_mcp_initialized'):
            return
        
        self._mcp_initialized = True
        
        try:
            print("Initializing Custom MCP connection...")
            
            import aiohttp
            
            # Your MCP server URL
            mcp_url = "http://localhost:3100/mcp"
            
            # Test connection and list tools
            async with aiohttp.ClientSession() as session:
                # Send tools/list request
                async with session.post(
                    mcp_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/list"
                    },
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Extract tools from response
                        tools_data = data.get('result', {}).get('tools', [])
                        
                        print(f"✓ Connected to Custom MCP: {len(tools_data)} tools available")
                        
                        # Store tools
                        self.mcp_tools = tools_data
                        self.mcp_url = mcp_url  # Store URL for future calls
                        
                        # Log tool names
                        for tool in tools_data[:5]:
                            print(f"  - {tool.get('name', 'unknown')}")
                        
                        if len(tools_data) > 5:
                            print(f"  ... and {len(tools_data) - 5} more")
                        
                        return True
                    else:
                        print(f"✗ MCP server returned status {response.status}")
                        return False
                
        except ImportError:
            print("✗ aiohttp not installed")
            print("  Run: pip install aiohttp")
            return False
        except Exception as e:
            print(f"✗ Error connecting to Custom MCP: {e}")
            import traceback
            traceback.print_exc()
            return False
    

    async def _call_mcp_tool(self, tool_name: str, arguments: dict):
        """
        Call an MCP tool via HTTP JSON-RPC
        """
        if not hasattr(self, 'mcp_url'):
            return None
        
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.mcp_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {
                            "name": tool_name,
                            "arguments": arguments
                        }
                    },
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('result')
                    else:
                        print(f"MCP tool call failed: {response.status}")
                        return None
                        
        except Exception as e:
            print(f"Error calling MCP tool {tool_name}: {e}")
        return None
    
    
    async def create_thread(self, call_sid: str) -> str:
        """
        Create conversation session for this call

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
        Send customer message to Assistants API, get response

        This is where the conversational AI happens:
        - Agent understands intent
        - Agent can call tools (if configured)
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