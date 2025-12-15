# DEVELOPMENT INSTRUCTIONS FOR CLAUDE CODE
## Building Twilio + OpenAI Realtime + OpenAI Agent Workflow Integration

---

## PROJECT OVERVIEW

Build a Python-based customer service voice system that integrates:
1. **Twilio** - Phone system (handles calls)
2. **OpenAI Realtime API** - Voice interface (audio ↔ text)
3. **OpenAI Agent Workflow** - Business logic brain (decisions, tools, context)

**Architecture**: 5-layer separation of concerns
- Twilio Layer → Voice Layer → Orchestration Layer → Business Logic Layer → Data Layer

---

## PROJECT STRUCTURE

Create this directory structure:

```
car-service-voice-system/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── config/
│   ├── __init__.py
│   ├── settings.py
│   └── constants.py
├── app.py                          # Main application entry point
├── layers/
│   ├── __init__.py
│   ├── voice_interface.py          # OpenAI Realtime integration
│   ├── orchestrator.py             # Session management & routing
│   └── business_logic.py           # Agent Workflow integration
├── services/
│   ├── __init__.py
│   ├── twilio_handler.py           # Twilio TwiML generation
│   ├── session_manager.py          # Session state management
│   └── context_enrichment.py      # Customer context handling
├── tools/
│   ├── __init__.py
│   ├── scheduling.py               # Appointment scheduling
│   ├── customer_data.py            # CRM operations
│   └── notifications.py            # SMS/email confirmations
├── models/
│   ├── __init__.py
│   ├── session.py                  # Session data models
│   ├── customer.py                 # Customer data models
│   └── appointment.py              # Appointment data models
├── utils/
│   ├── __init__.py
│   ├── logger.py                   # Logging configuration
│   ├── audio.py                    # Audio conversion utilities
│   └── validators.py               # Input validation
└── tests/
    ├── __init__.py
    ├── test_voice_interface.py
    ├── test_orchestrator.py
    ├── test_business_logic.py
    └── test_tools.py
```

---

## STEP 1: PROJECT INITIALIZATION

### Task 1.1: Create Project Scaffold

Create the directory structure above with all necessary files.

### Task 1.2: Create requirements.txt

Include these dependencies:
```
# Web Framework
flask==3.0.0
flask-cors==4.0.0

# WebSocket
websockets==12.0
flask-sock==0.7.0

# OpenAI
openai>=1.54.0

# Twilio
twilio==8.10.0

# Audio Processing
audioop-lts  # For Python 3.13+ compatibility

# Environment
python-dotenv==1.0.0

# Database (choose one)
# Option A: PostgreSQL
psycopg2-binary==2.9.9
sqlalchemy==2.0.23

# Option B: MongoDB
# pymongo==4.6.0

# Utilities
python-dateutil==2.8.2
pytz==2023.3
```

### Task 1.3: Create .env.example

```bash
# Twilio Configuration
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1234567890
WEBHOOK_URL=https://your-domain.com

# OpenAI Configuration
OPENAI_API_KEY=sk-your-api-key
OPENAI_REALTIME_MODEL=gpt-4o-realtime-preview-2024-10-01
OPENAI_WORKFLOW_MODEL=gpt-4-turbo
OPENAI_VOICE=alloy

# Agent Workflow Endpoint
AGENT_WORKFLOW_URL=https://your-agent-workflow-endpoint.com/chat

# Server Configuration
FLASK_PORT=5000
WEBSOCKET_PORT=8080
WEBSOCKET_HOST=0.0.0.0

# Database Configuration
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
# Or for MongoDB: mongodb://localhost:27017/dbname

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/app.log

# Business Rules
MAX_CONVERSATION_TURNS=25
MAX_TURN_DURATION_SECONDS=35
SESSION_TIMEOUT_MINUTES=30
```

### Task 1.4: Create .gitignore

Standard Python gitignore plus:
```
.env
*.log
logs/
static/audio/*
!static/audio/.gitkeep
__pycache__/
*.pyc
.pytest_cache/
.coverage
```

---

## STEP 2: CONFIGURATION LAYER

### Task 2.1: config/settings.py

Create configuration loader that:
- Loads environment variables
- Validates required settings
- Provides typed configuration objects
- Has separate configs for dev/staging/prod

**Requirements:**
```python
class Config:
    # All environment variables loaded
    # Validation on initialization
    # Type hints for all fields
    # Methods: validate(), to_dict()
```

### Task 2.2: config/constants.py

Define business constants:
```python
# Service types
SERVICE_TYPES = ["oil_change", "tire_rotation", "inspection", ...]

# Business hours
BUSINESS_HOURS = {
    "monday": ("08:00", "18:00"),
    "tuesday": ("08:00", "18:00"),
    ...
}

# Escalation keywords
ESCALATION_KEYWORDS = ["manager", "supervisor", "attorney", ...]

# Guardrails
PROHIBITED_TOPICS = ["guarantees", "diagnoses_without_inspection", ...]
```

---

## STEP 3: UTILITIES LAYER

### Task 3.1: utils/logger.py

Create logging setup:
- Console logging (development)
- File logging (production)
- Structured JSON logs
- Log rotation
- Context injection (call_sid, session_id)

**Requirements:**
```python
def setup_logger(name: str) -> logging.Logger:
    # Configure handlers
    # Set formatters
    # Return logger

def add_context(logger, **kwargs):
    # Add contextual info to all logs
    # Example: call_sid, customer_id
```

### Task 3.2: utils/audio.py

Audio conversion utilities:
- mulaw ↔ PCM16 conversion
- Base64 encoding/decoding
- Audio format validation
- Sample rate conversion if needed

**Requirements:**
```python
def mulaw_to_pcm16(data: bytes) -> bytes:
    # Use audioop for conversion

def pcm16_to_mulaw(data: bytes) -> bytes:
    # Use audioop for conversion

def encode_audio_base64(data: bytes) -> str:
    # Base64 encode

def decode_audio_base64(data: str) -> bytes:
    # Base64 decode
```

### Task 3.3: utils/validators.py

Input validation:
- Phone number validation
- Date/time validation
- Service type validation
- Customer input sanitization

---

## STEP 4: DATA MODELS

### Task 4.1: models/session.py

Create session data models:

```python
@dataclass
class VoiceSession:
    call_sid: str
    stream_sid: str
    websocket: WebSocket
    start_time: datetime
    status: str  # active, ended, error
    
@dataclass
class BusinessSession:
    conversation_id: str
    customer_id: str
    history: List[Message]
    context: Dict[str, Any]
    tool_results: List[ToolResult]
    workflow_state: str
    
@dataclass
class OrchestratorSession:
    session_id: str
    call_sid: str
    voice_session: VoiceSession
    business_session: BusinessSession
    start_time: datetime
    turn_count: int
    error_count: int
```

### Task 4.2: models/customer.py

Customer data model:
```python
@dataclass
class Customer:
    id: str
    name: str
    phone: str
    email: Optional[str]
    vehicle: Vehicle
    service_history: List[ServiceRecord]
    preferences: Dict[str, Any]
```

### Task 4.3: models/appointment.py

Appointment data model:
```python
@dataclass
class Appointment:
    id: str
    customer_id: str
    datetime: datetime
    service_type: str
    duration_minutes: int
    status: str  # scheduled, confirmed, completed, cancelled
    notes: Optional[str]
```

---

## STEP 5: VOICE INTERFACE LAYER

### Task 5.1: layers/voice_interface.py

**Class: VoiceInterfaceHandler**

**Purpose:** 
- Manage OpenAI Realtime API WebSocket connection
- Handle bidirectional audio streaming
- Convert between Twilio and OpenAI audio formats
- Emit events for transcriptions

**Key Methods:**
```python
async def connect(self, call_sid: str) -> bool:
    """Connect to OpenAI Realtime API"""
    # Create WebSocket connection
    # Configure session (voice, modalities, turn detection)
    # Return success/failure

async def handle_media_stream(self, twilio_ws, call_sid: str):
    """Main handler for Twilio media stream"""
    # Create two async tasks:
    #   1. Process Twilio → OpenAI (customer audio)
    #   2. Process OpenAI → Twilio (agent audio)
    # Handle both concurrently

async def _process_twilio_audio(self, twilio_ws, call_sid: str):
    """Forward customer audio to OpenAI"""
    # Receive from Twilio
    # Convert mulaw → PCM16
    # Send to OpenAI Realtime

async def _process_openai_audio(self, call_sid: str):
    """Forward agent audio to Twilio"""
    # Receive from OpenAI
    # Convert PCM16 → mulaw
    # Send to Twilio

async def on_transcription(self, call_sid: str, text: str):
    """Callback when customer speech is transcribed"""
    # Emit event to orchestrator
    # Pass transcription text

async def send_text_response(self, call_sid: str, text: str):
    """Send text to be spoken by OpenAI"""
    # Send to OpenAI for TTS
    # OpenAI will stream audio back

async def disconnect(self, call_sid: str):
    """Clean up connections"""
```

**Configuration:**
```python
REALTIME_CONFIG = {
    "modalities": ["text", "audio"],
    "instructions": """
        You are a voice interface. Your ONLY job is:
        1. Listen to customer speech
        2. Transcribe accurately
        3. Speak responses provided by the business system
        
        DO NOT make business decisions.
        DO NOT access customer data.
        DO NOT schedule appointments.
        
        You will receive text responses to speak.
        Speak them naturally and clearly.
    """,
    "voice": "alloy",
    "input_audio_format": "pcm16",
    "output_audio_format": "pcm16",
    "turn_detection": {
        "type": "server_vad",
        "threshold": 0.5,
        "silence_duration_ms": 500
    },
    "tools": []  # NO business tools!
}
```

**Important:** 
- Voice layer has NO business tools
- Only handles audio ↔ text conversion
- Emits transcription events to orchestrator
- Receives text responses from orchestrator to speak

---

## STEP 6: BUSINESS LOGIC LAYER

### Task 6.1: layers/business_logic.py

**Class: BusinessLogicHandler**

**Purpose:**
- Interface with OpenAI Agent Workflow
- Manage business session state
- Execute tool calls
- Generate context-aware responses

**Key Methods:**
```python
async def create_session(self, customer_context: Dict) -> str:
    """Create new business session"""
    # Initialize conversation with Agent Workflow
    # Store session state
    # Return conversation_id

async def process_message(
    self, 
    conversation_id: str, 
    message: str, 
    context: Dict
) -> AgentResponse:
    """Send message to Agent Workflow"""
    # POST to Agent Workflow endpoint
    # Include message + full context
    # Parse response (text, tool_calls, metadata)
    # Execute tool calls if any
    # Return complete response

async def execute_tools(self, tool_calls: List[ToolCall]) -> List[ToolResult]:
    """Execute business function calls"""
    # For each tool call:
    #   - Look up tool handler
    #   - Execute with args
    #   - Collect result
    # Return all results

def register_tool(self, name: str, handler: Callable):
    """Register a business tool"""
    # Add to tool registry

async def get_conversation_history(
    self, 
    conversation_id: str
) -> List[Message]:
    """Retrieve conversation history"""

async def end_session(self, conversation_id: str):
    """Clean up business session"""
    # Save final state
    # Persist to database
```

**Agent Workflow Request Format:**
```python
{
    "conversation_id": "CONV-12345",
    "message": "customer utterance",
    "context": {
        "customer": {
            "id": "12345",
            "name": "John Doe",
            "phone": "+1234567890",
            "vehicle": {
                "make": "Honda",
                "model": "Civic",
                "year": 2020
            }
        },
        "service_history": [
            {
                "date": "2024-10-15",
                "service_type": "oil_change",
                "cost": 59.99
            }
        ],
        "current_time": "2024-11-23T10:30:00Z",
        "conversation_turn": 3
    }
}
```

**Agent Workflow Response Format:**
```python
{
    "response_text": "Great! I see you're due for an oil change...",
    "tool_calls": [
        {
            "id": "call_123",
            "name": "check_availability",
            "args": {
                "service_type": "oil_change",
                "preferred_date": "2024-11-26"
            }
        }
    ],
    "metadata": {
        "confidence": 0.92,
        "intent": "schedule_appointment",
        "next_expected": "customer_time_choice"
    }
}
```

---

## STEP 7: ORCHESTRATION LAYER

### Task 7.1: layers/orchestrator.py

**Class: Orchestrator**

**Purpose:**
- Bridge between voice and business layers
- Manage all three session types
- Enrich context
- Route messages
- Apply guardrails
- Handle errors

**Key Methods:**
```python
async def start_call(
    self, 
    call_sid: str, 
    customer_phone: str
) -> OrchestratorSession:
    """Initialize all sessions for a new call"""
    # 1. Create voice session (OpenAI Realtime)
    # 2. Look up customer by phone
    # 3. Create business session (Agent Workflow)
    # 4. Link sessions in orchestrator session
    # 5. Return orchestrator session

async def handle_customer_message(
    self, 
    session_id: str, 
    transcription: str
):
    """Process customer utterance"""
    # 1. Get orchestrator session
    # 2. Enrich with customer context
    # 3. Send to business logic
    # 4. Wait for response
    # 5. Validate response (guardrails)
    # 6. Send to voice layer
    # 7. Update session metrics

async def enrich_context(
    self, 
    session_id: str, 
    base_message: str
) -> Dict:
    """Add customer context to message"""
    # Get customer data
    # Get service history
    # Get conversation history
    # Get current time/date
    # Return enriched context

async def apply_guardrails(
    self, 
    session_id: str, 
    response: str
) -> Tuple[bool, str]:
    """Validate agent response"""
    # Check for prohibited content
    # Check turn limits
    # Check for escalation triggers
    # Return (is_valid, reason)

async def handle_escalation(self, session_id: str, reason: str):
    """Handle escalation to human"""
    # Log escalation
    # Notify manager
    # Transfer call
    # Clean up sessions

async def end_call(self, session_id: str):
    """Clean up all sessions"""
    # Close voice session
    # End business session
    # Save conversation history
    # Update metrics
    # Clean up resources

def get_session(self, session_id: str) -> OrchestratorSession:
    """Retrieve orchestrator session"""

def list_active_sessions(self) -> List[OrchestratorSession]:
    """Get all active sessions"""
```

**Guardrails to Implement:**
```python
GUARDRAILS = {
    "max_turns": 25,
    "max_turn_duration": 35,  # seconds
    "prohibited_phrases": [
        "guaranteed",
        "diagnose without inspection",
        "insurance fraud"
    ],
    "escalation_keywords": [
        "lawyer", "attorney", "sue", 
        "manager", "supervisor",
        "unacceptable", "furious"
    ]
}
```

---

## STEP 8: TOOLS LAYER

### Task 8.1: tools/scheduling.py

**Functions:**
```python
async def schedule_appointment(
    customer_id: str,
    datetime: datetime,
    service_type: str,
    duration_minutes: int = 30
) -> Dict:
    """Schedule a new appointment"""
    # Check availability
    # Create appointment in database
    # Return confirmation
    
async def check_availability(
    service_type: str,
    preferred_date: str,
    preferred_time: Optional[str] = None
) -> Dict:
    """Check available appointment slots"""
    # Query calendar
    # Return available slots
    
async def cancel_appointment(
    appointment_id: str,
    reason: Optional[str] = None
) -> Dict:
    """Cancel an appointment"""
    # Update status in database
    # Send cancellation notification
```

### Task 8.2: tools/customer_data.py

**Functions:**
```python
async def get_customer_by_phone(phone: str) -> Optional[Customer]:
    """Look up customer by phone number"""
    
async def get_service_history(customer_id: str) -> List[ServiceRecord]:
    """Get customer's service history"""
    
async def update_customer_info(
    customer_id: str, 
    updates: Dict
) -> Customer:
    """Update customer information"""
    
async def get_vehicle_info(customer_id: str) -> Vehicle:
    """Get customer's vehicle details"""
```

### Task 8.3: tools/notifications.py

**Functions:**
```python
async def send_sms_confirmation(
    phone: str, 
    appointment: Appointment
) -> bool:
    """Send SMS appointment confirmation"""
    # Use Twilio SMS API
    
async def send_email_confirmation(
    email: str, 
    appointment: Appointment
) -> bool:
    """Send email confirmation"""
    
async def notify_manager(
    reason: str, 
    call_sid: str
) -> bool:
    """Notify manager of escalation"""
```

---

## STEP 9: SERVICES LAYER

### Task 9.1: services/twilio_handler.py

**Class: TwilioHandler**

**Methods:**
```python
def generate_initial_twiml(self) -> str:
    """Generate TwiML for initial call"""
    # Create VoiceResponse
    # Add Connect with Stream
    # Point to WebSocket endpoint
    # Return TwiML string

def generate_transfer_twiml(
    self, 
    transfer_number: str
) -> str:
    """Generate TwiML for call transfer"""
    # Create Dial
    # Add Number
    # Return TwiML
```

### Task 9.2: services/session_manager.py

**Class: SessionManager**

**Purpose:** Centralized session state management

**Methods:**
```python
def create_session(self, session_data: Dict) -> str:
    """Create new session, return session_id"""

def get_session(self, session_id: str) -> Optional[Dict]:
    """Retrieve session by ID"""

def update_session(self, session_id: str, updates: Dict):
    """Update session data"""

def delete_session(self, session_id: str):
    """Delete session"""

def list_active_sessions(self) -> List[Dict]:
    """Get all active sessions"""

async def cleanup_stale_sessions(self, timeout_minutes: int):
    """Clean up sessions older than timeout"""
```

### Task 9.3: services/context_enrichment.py

**Class: ContextEnricher**

**Purpose:** Add customer context to messages

**Methods:**
```python
async def enrich(
    self, 
    message: str, 
    customer_phone: str
) -> Dict:
    """Add full customer context"""
    # Look up customer
    # Get service history
    # Get vehicle info
    # Add timestamps
    # Return enriched payload
```

---

## STEP 10: MAIN APPLICATION

### Task 10.1: app.py

**Structure:**
```python
# Imports
from flask import Flask, request
import asyncio
import websockets
import threading

# Initialize Flask
app = Flask(__name__)

# Initialize all handlers
orchestrator = Orchestrator()
voice_handler = VoiceInterfaceHandler()
business_handler = BusinessLogicHandler()
twilio_handler = TwilioHandler()

# Register business tools
business_handler.register_tool("schedule_appointment", schedule_appointment)
business_handler.register_tool("check_availability", check_availability)
business_handler.register_tool("get_service_history", get_service_history)
# ... more tools

# Flask Routes
@app.route('/voice', methods=['POST'])
def voice_webhook():
    """Initial call webhook from Twilio"""
    # Get call info
    # Generate TwiML with Stream
    # Return TwiML

@app.route('/status', methods=['GET'])
def status():
    """Health check endpoint"""
    # Return system status

# WebSocket Handler
async def websocket_handler(websocket, path):
    """Handle Twilio media stream"""
    # Get first message (start event)
    # Extract call_sid
    # Start orchestrator session
    # Connect voice and business layers
    # Handle bidirectional streaming

# WebSocket Server
def start_websocket_server():
    """Start WebSocket server for media streams"""
    # Configure server
    # Start listening
    # Run forever

# Main
if __name__ == '__main__':
    # Start WebSocket server in background thread
    ws_thread = threading.Thread(
        target=start_websocket_server, 
        daemon=True
    )
    ws_thread.start()
    
    # Start Flask app
    app.run(host='0.0.0.0', port=5000)
```

---

## STEP 11: ERROR HANDLING

### Task 11.1: Implement Error Handlers

**In each layer, implement:**

```python
class LayerError(Exception):
    """Base error for this layer"""

class VoiceConnectionError(LayerError):
    """Voice layer connection failed"""

class BusinessLogicTimeout(LayerError):
    """Business logic took too long"""

class ToolExecutionError(LayerError):
    """Tool execution failed"""
```

**Error Handling Strategy:**
```python
try:
    # Operation
except VoiceConnectionError:
    # Retry 3x
    # If still fails → Escalate
    
except BusinessLogicTimeout:
    # Use fallback response
    # Log error
    # Continue conversation
    
except ToolExecutionError:
    # Return error to business logic
    # Let agent decide how to respond
```

---

## STEP 12: LOGGING & MONITORING

### Task 12.1: Implement Comprehensive Logging

**Log Levels:**
```python
# INFO: Session events
logger.info(f"[{call_sid}] Call started")
logger.info(f"[{call_sid}] Customer: {transcript}")
logger.info(f"[{call_sid}] Agent: {response}")

# DEBUG: Detailed flow
logger.debug(f"[{call_sid}] Tool call: {tool_name}({args})")
logger.debug(f"[{call_sid}] Tool result: {result}")

# WARNING: Issues but recoverable
logger.warning(f"[{call_sid}] Retry attempt {n}")

# ERROR: Failures
logger.error(f"[{call_sid}] Connection failed: {error}")
```

### Task 12.2: Implement Metrics

**Track:**
- Total calls
- Average call duration
- Successful bookings
- Escalation rate
- Tool success rate
- Error rate by type
- Response latency

---

## STEP 13: TESTING

### Task 13.1: Unit Tests

**For each layer, write tests:**
```python
# test_voice_interface.py
def test_audio_conversion():
    # Test mulaw ↔ PCM16

def test_connection():
    # Test OpenAI Realtime connection

# test_orchestrator.py
def test_session_creation():
    # Test session initialization

def test_context_enrichment():
    # Test context added correctly

def test_guardrails():
    # Test prohibited content blocked

# test_business_logic.py
def test_agent_workflow_call():
    # Test API call to Agent Workflow

def test_tool_execution():
    # Test tools execute correctly

# test_tools.py
def test_schedule_appointment():
    # Test appointment creation

def test_check_availability():
    # Test availability checking
```

### Task 13.2: Integration Tests

Test complete flows:
```python
async def test_complete_call_flow():
    # Simulate: Customer → Transcription → Business → Response
    
async def test_appointment_booking_flow():
    # Test multi-turn appointment booking
    
async def test_escalation_flow():
    # Test escalation trigger → transfer
```

---

## STEP 14: DOCUMENTATION

### Task 14.1: Create README.md

Include:
- Project overview
- Architecture diagram
- Setup instructions
- Environment variables
- Running the app
- Testing instructions
- Deployment guide

### Task 14.2: Create API Documentation

Document:
- Webhook endpoints
- WebSocket protocol
- Agent Workflow integration
- Tool function signatures
- Data models

---

## IMPLEMENTATION PRIORITIES

### Phase 1: Core Infrastructure (Week 1)
1. Project setup & dependencies
2. Configuration & utilities
3. Data models
4. Basic Flask app & WebSocket server

### Phase 2: Voice Layer (Week 2)
1. OpenAI Realtime integration
2. Audio conversion
3. Twilio WebSocket handling
4. Transcription events

### Phase 3: Business Layer (Week 2-3)
1. Agent Workflow API client
2. Tool framework
3. Core business tools (scheduling, customer lookup)
4. Tool execution

### Phase 4: Orchestration (Week 3)
1. Session management
2. Context enrichment
3. Message routing
4. Guardrails

### Phase 5: Integration & Testing (Week 4)
1. Connect all layers
2. End-to-end testing
3. Error handling
4. Performance optimization

### Phase 6: Production Readiness (Week 5)
1. Logging & monitoring
2. Database setup
3. Deployment scripts
4. Documentation

---

## KEY DESIGN PRINCIPLES

### 1. Separation of Concerns
- Voice layer ONLY handles audio
- Business layer ONLY handles logic
- Orchestrator ONLY routes and manages

### 2. Stateless Where Possible
- Tools are pure functions
- Layers don't store state internally
- Session state managed centrally

### 3. Async First
- All I/O operations async
- Concurrent processing where possible
- Non-blocking throughout

### 4. Error Resilience
- Retry with backoff
- Graceful degradation
- Clear error messages

### 5. Observable
- Comprehensive logging
- Metrics collection
- Session tracing

### 6. Testable
- Dependency injection
- Mock-friendly interfaces
- Isolated unit tests

---

## CRITICAL CONFIGURATIONS

### OpenAI Realtime (Voice Layer)

**DO:**
- Keep instructions simple and focused on voice I/O
- Use server-side VAD
- Set appropriate silence duration (500ms)
- Monitor connection health

**DON'T:**
- Add business tools to Realtime
- Put business logic in instructions
- Make it access customer data

### Agent Workflow (Business Layer)

**DO:**
- Give comprehensive business instructions
- Register ALL business tools
- Provide full customer context
- Enable conversation history

**DON'T:**
- Use it for voice processing
- Skip tool calls (always execute)
- Make decisions without tools

### Orchestrator

**DO:**
- Enrich ALL messages with context
- Apply guardrails BEFORE sending to voice
- Track metrics for every session
- Handle errors gracefully

**DON'T:**
- Skip context enrichment
- Forward responses without validation
- Ignore escalation signals

---

## SUCCESS CRITERIA

The implementation is successful when:

✅ Customer can make a call and have a natural conversation
✅ Voice transcription is accurate (>90%)
✅ Business logic makes correct decisions
✅ Appointments are successfully scheduled
✅ Escalations work smoothly
✅ End-to-end latency < 2 seconds
✅ Error rate < 5%
✅ All tests pass
✅ System handles 10+ concurrent calls
✅ Logs provide clear debugging info

---

## DEPLOYMENT CHECKLIST

Before deploying:
- [ ] All environment variables set
- [ ] Database migrations run
- [ ] SSL certificates configured
- [ ] Twilio webhooks pointed to production
- [ ] Agent Workflow endpoint configured
- [ ] OpenAI API keys valid
- [ ] Health check endpoint working
- [ ] Monitoring enabled
- [ ] Error alerting configured
- [ ] Backup/restore tested
- [ ] Load testing completed
- [ ] Documentation complete

---

## NOTES FOR CLAUDE CODE

**When building this project:**

1. **Follow the layer separation strictly**
   - Voice layer never makes business decisions
   - Business layer never touches audio
   - Keep responsibilities clear

2. **Start with data models**
   - Define types first
   - Use type hints everywhere
   - Makes later development easier

3. **Build bottom-up**
   - Utilities → Models → Layers → Integration
   - Test each piece before moving up

4. **Use async/await properly**
   - All I/O operations async
   - Use asyncio.gather for parallel ops
   - Handle cancellation gracefully

5. **Error handling is critical**
   - Every external call can fail
   - Implement retry logic
   - Provide fallbacks

6. **Logging is your friend**
   - Log session start/end
   - Log every customer message
   - Log every tool call
   - Include call_sid in all logs

7. **Test as you go**
   - Write tests alongside code
   - Test error cases
   - Test with real audio if possible

8. **Documentation matters**
   - Document complex logic
   - Explain architectural decisions
   - Keep README updated

---

This spec provides everything needed to build the integration from scratch. Each component has clear responsibilities, interfaces, and implementation guidance.