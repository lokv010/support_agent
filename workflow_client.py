"""
Agent Workflow Integration using OpenAI SDK

This is the BRAIN of the system.
Your published assistant has all the business logic.

IMPORTANT: Despite the variable name 'AGENT_WORKFLOW_ID', this must be an
OpenAI Assistant ID (starts with 'asst_'), NOT a Workflow ID (starts with 'wf_').

Workflows from Agent Builder cannot be used directly with the Assistants API.
You must create an Assistant at: https://platform.openai.com/assistants
"""

from openai import OpenAI
import os
import asyncio


class WorkflowClient:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.workflow_id = os.getenv('AGENT_WORKFLOW_ID')
        self.threads = {}  # call_sid → thread_id

        # Validate that we have an assistant ID, not a workflow ID
        if self.workflow_id and self.workflow_id.startswith('wf_'):
            raise ValueError(
                f"Invalid AGENT_WORKFLOW_ID: '{self.workflow_id}'. "
                f"Expected an Assistant ID starting with 'asst_', not a Workflow ID starting with 'wf_'. "
                f"Please create an OpenAI Assistant at https://platform.openai.com/assistants "
                f"and update your AGENT_WORKFLOW_ID environment variable. "
                f"See FIX_AUDIO_ISSUE.md for detailed instructions."
            )

    async def create_thread(self, call_sid: str) -> str:
        """
        Create conversation thread for this call

        Args:
            call_sid: Twilio call SID

        Returns:
            thread_id
        """
        # Run synchronous OpenAI SDK call in thread pool to avoid blocking
        thread = await asyncio.to_thread(self.client.beta.threads.create)
        self.threads[call_sid] = thread.id
        print(f"[{call_sid}] Created thread: {thread.id}")
        return thread.id

    async def send_message(self, call_sid: str, text: str) -> str:
        """
        Send message to Agent Workflow, get response

        This is where ALL the magic happens:
        - Workflow understands intent
        - Workflow fetches any context it needs
        - Workflow executes any actions
        - Workflow returns final response

        Args:
            call_sid: Call SID
            text: Customer message (from STT)

        Returns:
            Agent response text (for TTS)
        """
        thread_id = self.threads.get(call_sid)

        if not thread_id:
            thread_id = await self.create_thread(call_sid)

        print(f"[{call_sid}] → Workflow: {text}")

        # Add message to thread (run in thread pool to avoid blocking)
        await asyncio.to_thread(
            self.client.beta.threads.messages.create,
            thread_id=thread_id,
            role="user",
            content=text
        )

        # Run the assistant (run in thread pool to avoid blocking)
        # Note: self.workflow_id contains an assistant ID (asst_...), despite the variable name
        run = await asyncio.to_thread(
            self.client.beta.threads.runs.create_and_poll,
            thread_id=thread_id,
            assistant_id=self.workflow_id
        )

        # Get response (run in thread pool to avoid blocking)
        if run.status == 'completed':
            messages = await asyncio.to_thread(
                self.client.beta.threads.messages.list,
                thread_id=thread_id
            )

            # Get the latest assistant message
            for message in messages.data:
                if message.role == "assistant":
                    response_text = message.content[0].text.value
                    print(f"[{call_sid}] ← Workflow: {response_text}")
                    return response_text

        # Fallback
        return "I'm having trouble right now. Let me transfer you to our team."

    def cleanup(self, call_sid: str):
        """Clean up thread"""
        if call_sid in self.threads:
            del self.threads[call_sid]
            print(f"[{call_sid}] Thread cleaned up")
