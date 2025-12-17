"""
Agent Integration using OpenAI Agents SDK

This is the BRAIN of the system.
Simple agent with instructions and tools.
"""

from agents import Agent, Runner, InMemorySession
import os
import asyncio


class WorkflowClient:
    def __init__(self):
        # Define your agent with instructions
        # Customize this based on your use case (scheduling, support, etc.)
        self.agent = Agent(
            name="Support Assistant",
            instructions="""You are a helpful customer support assistant.

Your role is to:
- Greet customers warmly
- Answer their questions
- Help with scheduling appointments
- Provide information about services
- Handle requests professionally

Keep responses concise and conversational since this is a voice call.
""",
            # Add tools here if needed (e.g., check availability, schedule appointment)
            # tools=[check_availability, schedule_appointment]
        )

        # Track sessions per call
        self.sessions = {}  # call_sid → InMemorySession

    async def create_thread(self, call_sid: str) -> str:
        """
        Create conversation session for this call

        Args:
            call_sid: Twilio call SID

        Returns:
            session_id (same as call_sid)
        """
        session = InMemorySession(session_id=call_sid)
        self.sessions[call_sid] = session
        print(f"[{call_sid}] Created session")
        return call_sid

    async def send_message(self, call_sid: str, text: str) -> str:
        """
        Send message to Agent, get response

        This is where ALL the magic happens:
        - Agent understands intent
        - Agent can call tools if configured
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

        print(f"[{call_sid}] → Agent: {text}")

        # Run the agent with the message
        # Use asyncio.to_thread for the synchronous Runner.run_sync call
        result = await asyncio.to_thread(
            Runner.run_sync,
            self.agent,
            text,
            session=session
        )

        response_text = result.final_output
        print(f"[{call_sid}] ← Agent: {response_text}")

        return response_text

    def cleanup(self, call_sid: str):
        """Clean up session"""
        if call_sid in self.sessions:
            del self.sessions[call_sid]
            print(f"[{call_sid}] Session cleaned up")
