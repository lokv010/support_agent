"""Business constants for the car service voice AI system."""

# Service types
SERVICE_TYPES = [
    "oil_change",
    "tire_rotation",
    "brake_inspection",
    "brake_service",
    "battery_check",
    "battery_replacement",
    "air_filter",
    "cabin_filter",
    "transmission_service",
    "coolant_flush",
    "wheel_alignment",
    "state_inspection",
    "diagnostic",
    "general_maintenance"
]

# Business hours (24-hour format)
BUSINESS_HOURS = {
    "monday": ("08:00", "18:00"),
    "tuesday": ("08:00", "18:00"),
    "wednesday": ("08:00", "18:00"),
    "thursday": ("08:00", "18:00"),
    "friday": ("08:00", "18:00"),
    "saturday": ("09:00", "14:00"),
    "sunday": (None, None)  # Closed
}

# Escalation keywords (triggers transfer to human)
ESCALATION_KEYWORDS = [
    "manager",
    "supervisor",
    "human",
    "person",
    "attorney",
    "lawyer",
    "sue",
    "lawsuit",
    "furious",
    "angry",
    "unacceptable",
    "terrible",
    "worst"
]

# Prohibited phrases (guardrails)
PROHIBITED_PHRASES = [
    "guaranteed",
    "guarantee",
    "diagnose without inspection",
    "insurance fraud",
    "definitely fix",
    "100% certain",
    "never fail"
]

# Appointment durations (in minutes)
SERVICE_DURATIONS = {
    "oil_change": 30,
    "tire_rotation": 30,
    "brake_inspection": 45,
    "brake_service": 90,
    "battery_check": 15,
    "battery_replacement": 30,
    "air_filter": 15,
    "cabin_filter": 15,
    "transmission_service": 60,
    "coolant_flush": 45,
    "wheel_alignment": 60,
    "state_inspection": 45,
    "diagnostic": 60,
    "general_maintenance": 60
}

# Appointment slot interval (in minutes)
SLOT_INTERVAL_MINUTES = 30

# Session statuses
SESSION_STATUS_ACTIVE = "active"
SESSION_STATUS_ENDED = "ended"
SESSION_STATUS_ERROR = "error"
SESSION_STATUS_ESCALATED = "escalated"

# Appointment statuses
APPOINTMENT_STATUS_SCHEDULED = "scheduled"
APPOINTMENT_STATUS_CONFIRMED = "confirmed"
APPOINTMENT_STATUS_COMPLETED = "completed"
APPOINTMENT_STATUS_CANCELLED = "cancelled"
APPOINTMENT_STATUS_NO_SHOW = "no_show"
