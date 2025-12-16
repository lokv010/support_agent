"""Simple HTTP client for Agent Workflow communication."""

import aiohttp
from typing import Dict, Any
from config.settings import config
from utils.logger import setup_logger

logger = setup_logger(__name__)


class WorkflowClient:
    """HTTP client for OpenAI Agent Workflow."""

    def __init__(self):
        self.workflow_url = config.AGENT_WORKFLOW_URL
        self.api_key = config.AGENT_WORKFLOW_API_KEY

    async def send_message(
        self,
        conversation_id: str,
        message: str,
        customer_phone: str
    ) -> Dict[str, Any]:
        """
        Send message to Agent Workflow and get response.

        Args:
            conversation_id: Conversation ID
            message: Customer message
            customer_phone: Customer phone number (identifier)

        Returns:
            Agent Workflow response
        """
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        payload = {
            'conversation_id': conversation_id,
            'message': message,
            'customer_phone': customer_phone
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.workflow_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response.raise_for_status()
                    result = await response.json()
                    logger.info(f"Agent Workflow response received for conversation {conversation_id}")
                    return result

        except Exception as e:
            logger.error(f"Agent Workflow error: {e}")
            raise
