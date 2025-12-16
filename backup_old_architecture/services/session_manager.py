"""Centralized session state management."""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from models.session import OrchestratorSession
from config.settings import config
from utils.logger import setup_logger

logger = setup_logger(__name__)


class SessionManager:
    """Centralized session storage and management."""

    def __init__(self):
        self.sessions: Dict[str, OrchestratorSession] = {}

    def create_session(self, session: OrchestratorSession) -> str:
        """
        Create and store a new session.

        Args:
            session: OrchestratorSession object

        Returns:
            Session ID
        """
        self.sessions[session.session_id] = session
        logger.info(f"Session created: {session.session_id}")
        return session.session_id

    def get_session(self, session_id: str) -> Optional[OrchestratorSession]:
        """
        Retrieve session by ID.

        Args:
            session_id: Session ID

        Returns:
            OrchestratorSession or None
        """
        return self.sessions.get(session_id)

    def get_session_by_call_sid(self, call_sid: str) -> Optional[OrchestratorSession]:
        """
        Retrieve session by call SID.

        Args:
            call_sid: Twilio call SID

        Returns:
            OrchestratorSession or None
        """
        for session in self.sessions.values():
            if session.call_sid == call_sid:
                return session
        return None

    def update_session(self, session_id: str, session: OrchestratorSession):
        """
        Update session data.

        Args:
            session_id: Session ID
            session: Updated OrchestratorSession object
        """
        if session_id in self.sessions:
            self.sessions[session_id] = session
            logger.debug(f"Session updated: {session_id}")

    def delete_session(self, session_id: str):
        """
        Delete session.

        Args:
            session_id: Session ID
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Session deleted: {session_id}")

    def list_active_sessions(self) -> List[OrchestratorSession]:
        """
        Get all active sessions.

        Returns:
            List of active OrchestratorSession objects
        """
        active = [
            session for session in self.sessions.values()
            if session.end_time is None
        ]
        return active

    async def cleanup_stale_sessions(self):
        """Clean up sessions older than timeout."""
        timeout_minutes = config.SESSION_TIMEOUT_MINUTES
        cutoff_time = datetime.now() - timedelta(minutes=timeout_minutes)

        stale_sessions = []
        for session_id, session in self.sessions.items():
            if session.start_time < cutoff_time and session.end_time is None:
                stale_sessions.append(session_id)

        for session_id in stale_sessions:
            logger.warning(f"Cleaning up stale session: {session_id}")
            self.delete_session(session_id)

        if stale_sessions:
            logger.info(f"Cleaned up {len(stale_sessions)} stale sessions")

    def get_session_count(self) -> int:
        """
        Get total session count.

        Returns:
            Number of sessions
        """
        return len(self.sessions)


# Global session manager instance
session_manager = SessionManager()
