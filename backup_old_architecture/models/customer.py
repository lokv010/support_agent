"""Customer data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Vehicle:
    """Customer vehicle information."""

    make: str
    model: str
    year: int
    vin: Optional[str] = None
    color: Optional[str] = None
    mileage: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'make': self.make,
            'model': self.model,
            'year': self.year,
            'vin': self.vin,
            'color': self.color,
            'mileage': self.mileage
        }


@dataclass
class ServiceRecord:
    """Historical service record."""

    id: str
    date: str  # ISO format date
    service_type: str
    cost: float
    mileage: Optional[int] = None
    notes: Optional[str] = None
    technician: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'date': self.date,
            'service_type': self.service_type,
            'cost': self.cost,
            'mileage': self.mileage,
            'notes': self.notes,
            'technician': self.technician
        }


@dataclass
class Customer:
    """Customer information."""

    id: str
    name: str
    phone: str
    email: Optional[str] = None
    vehicle: Optional[Vehicle] = None
    service_history: List[ServiceRecord] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    last_service_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'email': self.email,
            'vehicle': self.vehicle.to_dict() if self.vehicle else None,
            'service_history': [record.to_dict() for record in self.service_history],
            'preferences': self.preferences,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_service_date': self.last_service_date
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Customer':
        """Create Customer from dictionary."""
        vehicle_data = data.get('vehicle')
        vehicle = Vehicle(**vehicle_data) if vehicle_data else None

        service_history = [
            ServiceRecord(**record) for record in data.get('service_history', [])
        ]

        created_at = None
        if data.get('created_at'):
            try:
                created_at = datetime.fromisoformat(data['created_at'])
            except (ValueError, AttributeError):
                pass

        return cls(
            id=data['id'],
            name=data['name'],
            phone=data['phone'],
            email=data.get('email'),
            vehicle=vehicle,
            service_history=service_history,
            preferences=data.get('preferences', {}),
            created_at=created_at,
            last_service_date=data.get('last_service_date')
        )
