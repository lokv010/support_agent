"""Session data models for the car service voice AI system."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class VoiceSession:
    """Voice layer session (OpenAI Realtime connection)."""

    call_sid: str
    stream_sid: str
    customer_phone: str
    start_time: datetime
    status: str  # active, ended, error
    websocket: Any = None  # WebSocket connection
    openai_ws: Any = None  # OpenAI Realtime WebSocket

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'call_sid': self.call_sid,
            'stream_sid': self.stream_sid,
            'customer_phone': self.customer_phone,
            'start_time': self.start_time.isoformat(),
            'status': self.status
        }


@dataclass
class Message:
    """Conversation message."""

    role: str  # user, assistant, system
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class ToolResult:
    """Tool execution result."""

    tool_name: str
    args: Dict[str, Any]
    result: Any
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'tool_name': self.tool_name,
            'args': self.args,
            'result': self.result,
            'timestamp': self.timestamp.isoformat(),
            'success': self.success,
            'error': self.error
        }


@dataclass
class BusinessSession:
    """Business logic session (Agent Workflow conversation)."""

    conversation_id: str
    customer_id: Optional[str]
    customer_phone: str
    history: List[Message] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    tool_results: List[ToolResult] = field(default_factory=list)
    workflow_state: str = "active"  # active, completed, error

    def add_message(self, role: str, content: str):
        """Add message to history."""
        self.history.append(Message(role=role, content=content))

    def add_tool_result(self, tool_name: str, args: Dict[str, Any], result: Any, success: bool = True, error: Optional[str] = None):
        """Add tool result."""
        self.tool_results.append(ToolResult(
            tool_name=tool_name,
            args=args,
            result=result,
            success=success,
            error=error
        ))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'conversation_id': self.conversation_id,
            'customer_id': self.customer_id,
            'customer_phone': self.customer_phone,
            'history': [msg.to_dict() for msg in self.history],
            'context': self.context,
            'tool_results': [tr.to_dict() for tr in self.tool_results],
            'workflow_state': self.workflow_state
        }


@dataclass
class OrchestratorSession:
    """Orchestrator session linking voice and business layers."""

    session_id: str
    call_sid: str
    voice_session: VoiceSession
    business_session: BusinessSession
    start_time: datetime
    turn_count: int = 0
    error_count: int = 0
    escalation_triggered: bool = False
    end_time: Optional[datetime] = None

    def increment_turn(self):
        """Increment turn counter."""
        self.turn_count += 1

    def increment_error(self):
        """Increment error counter."""
        self.error_count += 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'session_id': self.session_id,
            'call_sid': self.call_sid,
            'voice_session': self.voice_session.to_dict(),
            'business_session': self.business_session.to_dict(),
            'start_time': self.start_time.isoformat(),
            'turn_count': self.turn_count,
            'error_count': self.error_count,
            'escalation_triggered': self.escalation_triggered,
            'end_time': self.end_time.isoformat() if self.end_time else None
        }
