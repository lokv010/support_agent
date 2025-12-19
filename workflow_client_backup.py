"""
Agent Integration using OpenAI Assistant API with MCP Tools

This is the BRAIN of the system.
OpenAI Assistant with tools from MCP server (Zapier).
"""

import os
import asyncio
import json
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class WorkflowClient:
    def __init__(self):
        """Initialize OpenAI Assistant with MCP tools"""
        self.openai_client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.assistant_id: Optional[str] = None
        self.mcp_session: Optional[ClientSession] = None
        self.mcp_tools: List[Dict[str, Any]] = []

        # Track threads per call
        self.threads = {}  # call_sid → thread_id

        # Initialize flag
        self._initialized = False

    async def initialize(self):
        """Initialize MCP connection and create Assistant"""
        if self._initialized:
            return

        print("Initializing MCP server connection...")

        # Connect to MCP server (Zapier)
        server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-zapier"],
            env={
                "ZAPIER_API_KEY": os.getenv('ZAPIER_API_KEY', '')
            }
        )

        try:
            # Create MCP client session
            stdio_transport = await stdio_client(server_params)
            self.mcp_session = ClientSession(stdio_transport[0], stdio_transport[1])

            await self.mcp_session.initialize()
            print("✓ MCP server connected")

            # Get available tools from MCP server
            tools_response = await self.mcp_session.list_tools()
            print(f"✓ Found {len(tools_response.tools)} tools from MCP server")

            # Convert MCP tools to OpenAI function format
            self.mcp_tools = self._convert_mcp_tools_to_openai(tools_response.tools)

            # Create OpenAI Assistant with MCP tools
            await self._create_assistant()

            self._initialized = True
            print("✓ Assistant initialized with MCP tools")

        except Exception as e:
            print(f"Error initializing MCP: {e}")
            print("Continuing without MCP tools...")
            # Create assistant without tools if MCP fails
            await self._create_assistant()
            self._initialized = True

    def _convert_mcp_tools_to_openai(self, mcp_tools) -> List[Dict[str, Any]]:
        """Convert MCP tools to OpenAI function format"""
        openai_tools = []

        for tool in mcp_tools:
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or f"Execute {tool.name}",
                    "parameters": tool.inputSchema if hasattr(tool, 'inputSchema') else {
                        "type": "object",
                        "properties": {}
                    }
                }
            }
            openai_tools.append(openai_tool)
            print(f"  - {tool.name}: {tool.description}")

        return openai_tools

    async def _create_assistant(self):
        """Create OpenAI Assistant"""
        try:
            assistant = await self.openai_client.beta.assistants.create(
                name="Support Assistant with Zapier",
                instructions="""You are a helpful customer support assistant with access to Zapier automation tools.

Your role is to:
- Greet customers warmly
- Answer their questions
- Help with scheduling appointments
- Send notifications and updates via Zapier
- Automate tasks using available tools
- Provide information about services
- Handle requests professionally

You have access to Zapier tools to:
- Send emails, SMS, and notifications
- Create calendar events
- Update CRM records
- Trigger workflows
- And more based on configured Zapier actions

Keep responses concise and conversational since this is a voice call.
When you need to perform an action, use the available tools.
Always confirm actions before executing them.
""",
                model="gpt-4o-2024-11-20",  # Latest model with function calling
                tools=self.mcp_tools if self.mcp_tools else []
            )

            self.assistant_id = assistant.id
            print(f"✓ Created Assistant: {assistant.id}")

        except Exception as e:
            print(f"Error creating assistant: {e}")
            raise

    async def create_thread(self, call_sid: str) -> str:
        """
        Create conversation thread for this call

        Args:
            call_sid: Twilio call SID

        Returns:
            thread_id
        """
        # Ensure initialization
        if not self._initialized:
            await self.initialize()

        try:
            thread = await self.openai_client.beta.threads.create()
            self.threads[call_sid] = thread.id
            print(f"[{call_sid}] Created thread: {thread.id}")
            return thread.id
        except Exception as e:
            print(f"[{call_sid}] Error creating thread: {e}")
            raise

    async def send_message(self, call_sid: str, text: str) -> str:
        """
        Send message to Assistant, get response

        This is where ALL the magic happens:
        - Assistant understands intent
        - Assistant can call MCP tools
        - Assistant generates response

        Args:
            call_sid: Call SID
            text: Customer message (from STT)

        Returns:
            Assistant response text (for TTS)
        """
        # Ensure initialization
        if not self._initialized:
            await self.initialize()

        thread_id = self.threads.get(call_sid)

        if not thread_id:
            thread_id = await self.create_thread(call_sid)

        print(f"[{call_sid}] → Assistant: {text}")

        try:
            # Add message to thread
            await self.openai_client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=text
            )

            # Run assistant
            run = await self.openai_client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=self.assistant_id
            )

            # Wait for completion and handle tool calls
            response_text = await self._wait_for_run_completion(call_sid, thread_id, run.id)

            print(f"[{call_sid}] ← Assistant: {response_text}")
            return response_text

        except Exception as e:
            print(f"[{call_sid}] Error in send_message: {e}")
            return "I apologize, but I'm having trouble processing your request. Could you please try again?"

    async def _wait_for_run_completion(self, call_sid: str, thread_id: str, run_id: str) -> str:
        """
        Wait for run to complete, handle tool calls if needed

        Args:
            call_sid: Call SID
            thread_id: Thread ID
            run_id: Run ID

        Returns:
            Final response text
        """
        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Check run status
            run = await self.openai_client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run_id
            )

            print(f"[{call_sid}] Run status: {run.status}")

            if run.status == "completed":
                # Get the latest message
                messages = await self.openai_client.beta.threads.messages.list(
                    thread_id=thread_id,
                    order="desc",
                    limit=1
                )

                if messages.data:
                    message = messages.data[0]
                    if message.content:
                        # Extract text from message content
                        text_content = next(
                            (block.text.value for block in message.content
                             if hasattr(block, 'text')),
                            "I'm ready to help!"
                        )
                        return text_content

                return "I'm ready to help!"

            elif run.status == "requires_action":
                # Handle tool calls
                print(f"[{call_sid}] Handling tool calls...")
                await self._handle_tool_calls(call_sid, thread_id, run_id, run)

            elif run.status in ["failed", "cancelled", "expired"]:
                print(f"[{call_sid}] Run {run.status}: {run.last_error}")
                return "I encountered an issue. Let me try to help you differently."

            # Wait before checking again
            await asyncio.sleep(0.5)

        print(f"[{call_sid}] Max iterations reached")
        return "I'm taking longer than expected. Could you please repeat that?"

    async def _handle_tool_calls(self, call_sid: str, thread_id: str, run_id: str, run):
        """
        Execute tool calls via MCP server and submit results

        Args:
            call_sid: Call SID
            thread_id: Thread ID
            run_id: Run ID
            run: Run object with required_action
        """
        tool_outputs = []

        if not run.required_action or not run.required_action.submit_tool_outputs:
            return

        tool_calls = run.required_action.submit_tool_outputs.tool_calls

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)

            print(f"[{call_sid}] Executing tool: {function_name}")
            print(f"[{call_sid}] Arguments: {function_args}")

            try:
                # Execute tool via MCP
                if self.mcp_session:
                    result = await self.mcp_session.call_tool(
                        function_name,
                        arguments=function_args
                    )

                    # Extract result content
                    output = json.dumps({
                        "success": True,
                        "result": result.content if hasattr(result, 'content') else str(result)
                    })
                else:
                    output = json.dumps({
                        "success": False,
                        "error": "MCP session not available"
                    })

                print(f"[{call_sid}] Tool result: {output}")

            except Exception as e:
                print(f"[{call_sid}] Tool execution error: {e}")
                output = json.dumps({
                    "success": False,
                    "error": str(e)
                })

            tool_outputs.append({
                "tool_call_id": tool_call.id,
                "output": output
            })

        # Submit tool outputs
        if tool_outputs:
            await self.openai_client.beta.threads.runs.submit_tool_outputs(
                thread_id=thread_id,
                run_id=run_id,
                tool_outputs=tool_outputs
            )
            print(f"[{call_sid}] Submitted {len(tool_outputs)} tool outputs")

    def cleanup(self, call_sid: str):
        """Clean up thread"""
        if call_sid in self.threads:
            # Note: We don't delete the thread immediately in case we need to review it
            # OpenAI will clean up old threads automatically
            del self.threads[call_sid]
            print(f"[{call_sid}] Thread cleaned up")

    async def shutdown(self):
        """Shutdown MCP session"""
        if self.mcp_session:
            try:
                await self.mcp_session.close()
                print("✓ MCP session closed")
            except Exception as e:
                print(f"Error closing MCP session: {e}")
