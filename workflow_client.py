"""
Agent Workflow Integration using OpenAI SDK

This is the BRAIN of the system.
Your published workflow has all the business logic.
"""

from openai import OpenAI
import os


class WorkflowClient:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.workflow_id = os.getenv('AGENT_WORKFLOW_ID')
        self.threads = {}  # call_sid → thread_id

    def create_thread(self, call_sid: str) -> str:
        """
        Create conversation thread for this call

        Args:
            call_sid: Twilio call SID

        Returns:
            thread_id
        """
        thread = self.client.beta.threads.create()
        self.threads[call_sid] = thread.id
        print(f"[{call_sid}] Created thread: {thread.id}")
        return thread.id

    def send_message(self, call_sid: str, text: str) -> str:
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
            thread_id = self.create_thread(call_sid)

        print(f"[{call_sid}] → Workflow: {text}")

        # Add message to thread
        self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=text
        )

        # Run the workflow
        run = self.client.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=self.workflow_id
        )

        # Get response
        if run.status == 'completed':
            messages = self.client.beta.threads.messages.list(
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
