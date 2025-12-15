"""Orchestrator layer for routing between voice and business logic."""

import uuid
from datetime import datetime
from typing import Tuple
from models.session import VoiceSession, BusinessSession, OrchestratorSession
from layers.voice_interface import VoiceInterfaceHandler
from layers.workflow_client import WorkflowClient
from services.session_manager import session_manager
from config.constants import ESCALATION_KEYWORDS, PROHIBITED_PHRASES
from config.settings import config
from utils.logger import setup_logger, ContextLogger

logger = setup_logger(__name__)


class Orchestrator:
    """Orchestrator for managing sessions and routing messages."""

    def __init__(self, voice_handler: VoiceInterfaceHandler, workflow_client: WorkflowClient):
        self.voice_handler = voice_handler
        self.workflow_client = workflow_client

    async def start_call(self, call_sid: str, stream_sid: str, customer_phone: str) -> OrchestratorSession:
        """
        Initialize session for new call.

        Args:
            call_sid: Twilio call SID
            stream_sid: Twilio stream SID
            customer_phone: Customer phone number

        Returns:
            OrchestratorSession
        """
        ctx_logger = ContextLogger(logger, call_sid=call_sid)
        ctx_logger.info(f"Starting call from {customer_phone}")

        # Create voice session
        voice_session = VoiceSession(
            call_sid=call_sid,
            stream_sid=stream_sid,
            customer_phone=customer_phone,
            start_time=datetime.now(),
            status='active'
        )

        # Create business session
        conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
        business_session = BusinessSession(
            conversation_id=conversation_id,
            customer_id=None,  # Will be looked up by Agent Workflow
            customer_phone=customer_phone
        )

        # Create orchestrator session
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        orchestrator_session = OrchestratorSession(
            session_id=session_id,
            call_sid=call_sid,
            voice_session=voice_session,
            business_session=business_session,
            start_time=datetime.now()
        )

        # Store session
        session_manager.create_session(orchestrator_session)

        ctx_logger.info(f"Session created: {session_id}")
        return orchestrator_session

    async def handle_customer_message(self, call_sid: str, transcription: str):
        """
        Process customer transcription.

        Args:
            call_sid: Call SID
            transcription: Customer's transcribed message
        """
        ctx_logger = ContextLogger(logger, call_sid=call_sid)

        # Get session
        session = session_manager.get_session_by_call_sid(call_sid)
        if not session:
            ctx_logger.error("Session not found")
            return

        # Increment turn
        session.increment_turn()

        # Check turn limit
        if session.turn_count > config.MAX_CONVERSATION_TURNS:
            ctx_logger.warning("Turn limit exceeded")
            await self._handle_escalation(session, "Turn limit exceeded")
            return

        # Apply guardrails
        should_escalate, reason = await self._check_guardrails(transcription)
        if should_escalate:
            ctx_logger.warning(f"Guardrail triggered: {reason}")
            await self._handle_escalation(session, reason)
            return

        # Send to Agent Workflow (NO context enrichment - just phone!)
        try:
            result = await self.workflow_client.send_message(
                conversation_id=session.business_session.conversation_id,
                message=transcription,
                customer_phone=session.voice_session.customer_phone
            )

            # Get response from workflow
            response_text = result.get('response_text', result.get('response', ''))

            if response_text:
                # Validate response
                is_valid, validation_reason = await self._validate_response(response_text)

                if not is_valid:
                    ctx_logger.warning(f"Response validation failed: {validation_reason}")
                    response_text = "Let me transfer you to someone who can better assist you."
                    await self._handle_escalation(session, validation_reason)
                else:
                    # Send to voice layer
                    await self.voice_handler.send_text_response(call_sid, response_text)

        except Exception as e:
            ctx_logger.error(f"Error processing message: {e}")
            session.increment_error()
            await self.voice_handler.send_text_response(
                call_sid,
                "I'm having technical difficulties. Let me transfer you to an agent."
            )
            await self._handle_escalation(session, f"Error: {str(e)}")

    async def _check_guardrails(self, text: str) -> Tuple[bool, str]:
        """
        Check if text triggers guardrails.

        Args:
            text: Text to check

        Returns:
            (should_escalate, reason)
        """
        text_lower = text.lower()

        # Check for escalation keywords
        for keyword in ESCALATION_KEYWORDS:
            if keyword in text_lower:
                return True, f"Escalation keyword: {keyword}"

        return False, ""

    async def _validate_response(self, text: str) -> Tuple[bool, str]:
        """
        Validate agent response doesn't contain prohibited content.

        Args:
            text: Response text

        Returns:
            (is_valid, reason)
        """
        text_lower = text.lower()

        # Check for prohibited phrases
        for phrase in PROHIBITED_PHRASES:
            if phrase in text_lower:
                return False, f"Prohibited phrase: {phrase}"

        return True, ""

    async def _handle_escalation(self, session: OrchestratorSession, reason: str):
        """
        Handle escalation to human agent.

        Args:
            session: Orchestrator session
            reason: Escalation reason
        """
        ctx_logger = ContextLogger(logger, call_sid=session.call_sid)
        ctx_logger.warning(f"Escalating call: {reason}")

        session.escalation_triggered = True

        # Notify manager
        from tools.notifications import notify_manager
        await notify_manager(
            reason=reason,
            call_sid=session.call_sid,
            customer_phone=session.voice_session.customer_phone
        )

        # End session
        await self.end_call(session.call_sid)

    async def end_call(self, call_sid: str):
        """
        End call and cleanup.

        Args:
            call_sid: Call SID
        """
        ctx_logger = ContextLogger(logger, call_sid=call_sid)

        session = session_manager.get_session_by_call_sid(call_sid)
        if not session:
            return

        # Mark end time
        session.end_time = datetime.now()
        session.voice_session.status = 'ended'
        session.business_session.workflow_state = 'completed'

        ctx_logger.info(f"Call ended - Duration: {session.end_time - session.start_time}, Turns: {session.turn_count}")

        # Disconnect voice interface
        await self.voice_handler.disconnect(call_sid)

        # Could save to database here
        # For now, just keep in memory

        ctx_logger.info("Session cleanup complete")
