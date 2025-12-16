"""Appointment data models."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class Appointment:
    """Service appointment information."""

    id: str
    customer_id: str
    datetime: datetime
    service_type: str
    duration_minutes: int = 30
    status: str = 'scheduled'  # scheduled, confirmed, completed, cancelled, no_show
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'customer_id': self.customer_id,
            'datetime': self.datetime.isoformat(),
            'service_type': self.service_type,
            'duration_minutes': self.duration_minutes,
            'status': self.status,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Appointment':
        """Create Appointment from dictionary."""
        dt = data['datetime']
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))

        created_at = None
        if data.get('created_at'):
            try:
                created_at = datetime.fromisoformat(data['created_at'])
            except (ValueError, AttributeError):
                pass

        return cls(
            id=data['id'],
            customer_id=data['customer_id'],
            datetime=dt,
            service_type=data['service_type'],
            duration_minutes=data.get('duration_minutes', 30),
            status=data.get('status', 'scheduled'),
            notes=data.get('notes'),
            created_at=created_at
        )


@dataclass
class AppointmentSlot:
    """Available appointment slot."""

    date: str  # YYYY-MM-DD
    time: str  # HH:MM (24-hour format)
    duration_minutes: int
    available: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'date': self.date,
            'time': self.time,
            'duration_minutes': self.duration_minutes,
            'available': self.available
        }
