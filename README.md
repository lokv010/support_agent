# Car Service Voice AI System

AI-powered voice system for car service centers integrating Twilio phone calls, OpenAI Realtime API for voice, and OpenAI Agent Workflow for business intelligence.

## Overview

This system enables natural voice conversations between customers and an AI assistant for:
- Scheduling service appointments
- Checking service history
- Getting appointment availability
- Receiving SMS confirmations
- Escalating to human agents when needed

### Architecture

```
Customer Call → Twilio → Voice Layer → Orchestrator → Agent Workflow
                                                            ↓
                                                    Your Tool APIs
                                                            ↓
                                                        Database
```

**Key Design Principle:** Your code is thin. Agent Workflow is smart.

### Components

| Layer | Purpose | Complexity |
|-------|---------|------------|
| **Voice Layer** | Audio ↔ Text conversion (OpenAI Realtime) | Low |
| **Orchestrator** | Message routing + guardrails | Low |
| **Workflow Client** | HTTP client to Agent Workflow | Low |
| **Tool APIs** | Endpoints Agent Workflow calls | Low |
| **Agent Workflow** | Business intelligence (OpenAI managed) | High ✅ |

---

## Features

### Customer Experience
- ✅ Natural voice conversations
- ✅ Low latency (<2 seconds end-to-end)
- ✅ Voice activity detection
- ✅ Appointment scheduling
- ✅ SMS confirmations
- ✅ Escalation to humans

### Business Features
- ✅ Customer lookup
- ✅ Service history access
- ✅ Real-time availability checking
- ✅ Automatic appointment booking
- ✅ Multi-turn conversations
- ✅ Intent understanding

### Technical Features
- ✅ Async/await throughout
- ✅ Comprehensive logging
- ✅ Error handling & retries
- ✅ Guardrails & validation
- ✅ Concurrent call support

---

## Prerequisites

- Python 3.10+
- Twilio account
- OpenAI API key
- Published OpenAI Agent Workflow
- Database (PostgreSQL or MongoDB)
- Public HTTPS endpoint (for webhooks)

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/your-org/car-service-voice-ai.git
cd car-service-voice-ai

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

Required variables:
```bash
# Twilio
TWILIO_ACCOUNT_SID=ACxxxxx
TWILIO_AUTH_TOKEN=your_token
TWILIO_PHONE_NUMBER=+1234567890
WEBHOOK_URL=https://your-domain.com

# OpenAI
OPENAI_API_KEY=sk-xxxxx
OPENAI_REALTIME_MODEL=gpt-4o-realtime-preview-2024-10-01
OPENAI_VOICE=alloy

# Agent Workflow
AGENT_WORKFLOW_URL=https://your-workflow.openai.com
AGENT_WORKFLOW_API_KEY=sk-workflow-xxxxx

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
```

### 3. Configure Agent Workflow

In your OpenAI Agent Workflow dashboard:

**System Instructions:**
```
You are a car service center AI assistant.

When a customer contacts us:
1. Look up their information using get_customer_by_phone
2. Check their service history using get_service_history
3. Help them schedule using check_availability and schedule_appointment

Use tools to get real data. Never make up information.
```

**Register Tools:**
- `get_customer_by_phone` → `https://your-domain.com/tools/get-customer`
- `get_service_history` → `https://your-domain.com/tools/get-history`
- `check_availability` → `https://your-domain.com/tools/check-availability`
- `schedule_appointment` → `https://your-domain.com/tools/schedule-appointment`

### 4. Run the Application

```bash
python app.py
```

You should see:
```
======================================================================
STARTING CAR SERVICE VOICE SYSTEM
======================================================================
OpenAI Realtime Model: gpt-4o-realtime-preview-2024-10-01
Agent Workflow URL: https://your-workflow.openai.com
Tools Base URL: https://your-domain.com/tools
======================================================================
 * Running on http://0.0.0.0:5000
```

### 5. Configure Twilio

In Twilio Console:
1. Go to Phone Numbers → Your Number
2. Set Voice Webhook: `https://your-domain.com/voice`
3. Set to HTTP POST
4. Save

### 6. Test

Call your Twilio number and say:
> "I need an oil change"

The system should:
1. Look you up by phone
2. Check your service history
3. Find available slots
4. Offer appointment times

---

## Project Structure

```
car-service-voice-system/
├── app.py                          # Main application
├── requirements.txt                # Dependencies
├── .env.example                    # Environment template
│
├── layers/
│   ├── voice_interface.py          # OpenAI Realtime handler
│   ├── orchestrator.py             # Message router (~50 lines)
│   └── workflow_client.py          # Agent Workflow client (~20 lines)
│
├── tools/
│   ├── api.py                      # Tool endpoints (Flask routes)
│   ├── customer.py                 # Customer database operations
│   ├── scheduling.py               # Appointment operations
│   └── notifications.py            # SMS/email
│
├── models/
│   ├── session.py                  # Session models
│   ├── customer.py                 # Customer model
│   └── appointment.py              # Appointment model
│
├── utils/
│   ├── logger.py                   # Logging utilities
│   └── audio.py                    # Audio conversion
│
├── config/
│   ├── settings.py                 # Configuration
│   └── constants.py                # Business constants
│
└── tests/
    ├── test_voice.py
    ├── test_orchestrator.py
    └── test_tools.py
```

---

## How It Works

### Complete Call Flow

```
1. Customer calls Twilio number
   ↓
2. Twilio hits /voice webhook
   ↓
3. Your app returns TwiML with <Stream>
   ↓
4. WebSocket opens to /media-stream
   ↓
5. Voice Layer:
   - Connects to OpenAI Realtime
   - Starts bidirectional audio streaming
   ↓
6. Customer speaks: "I need an oil change"
   ↓
7. Voice Layer:
   - Receives audio from Twilio
   - Converts mulaw → PCM16
   - Sends to OpenAI Realtime
   - OpenAI transcribes
   - Emits transcription event
   ↓
8. Orchestrator:
   - Receives transcription
   - Applies guardrails
   - Routes to Agent Workflow
   ↓
9. Agent Workflow (OpenAI managed):
   - Understands intent: "schedule_oil_change"
   - Calls YOUR tool: POST /tools/get-customer
   - Gets customer info
   - Calls YOUR tool: POST /tools/get-history
   - Gets service history
   - Calls YOUR tool: POST /tools/check-availability
   - Gets available slots
   - Generates response
   ↓
10. Orchestrator:
    - Receives final response
    - Validates (guardrails)
    - Sends to Voice Layer
    ↓
11. Voice Layer:
    - Receives text
    - Sends to OpenAI Realtime for TTS
    - OpenAI converts to speech
    - Streams audio to Twilio
    ↓
12. Customer hears:
    "We have Tuesday at 9 AM or Thursday at 2 PM available"
```

### What Each Layer Does

**Voice Layer (OpenAI Realtime):**
- ✅ Audio ↔ Text conversion
- ✅ Voice Activity Detection
- ✅ Natural speech synthesis
- ❌ NO business logic

**Orchestrator:**
- ✅ Route messages
- ✅ Apply guardrails
- ✅ Manage sessions
- ❌ NO context enrichment (Agent Workflow does this!)

**Agent Workflow Client:**
- ✅ HTTP client
- ✅ Send message + phone
- ✅ Receive final response
- ❌ NO tool execution (Agent Workflow does this!)

**Agent Workflow (OpenAI):**
- ✅ Understand intent
- ✅ Fetch context via YOUR tools
- ✅ Execute operations via YOUR tools
- ✅ Multi-step reasoning
- ✅ Generate response

**Your Tool APIs:**
- ✅ Provide data when asked
- ✅ Execute operations
- ✅ Return results

---

## API Endpoints

### Twilio Webhooks

**POST /voice**
- Initial call webhook
- Returns TwiML with media stream

**WebSocket /media-stream**
- Bidirectional audio streaming
- Connects to OpenAI Realtime

### Tool Endpoints (Called by Agent Workflow)

**POST /tools/get-customer**
```json
Request:
{
  "phone": "+1234567890"
}

Response:
{
  "found": true,
  "customer_id": "cust_001",
  "name": "John Doe",
  "vehicle": {
    "make": "Honda",
    "model": "Civic",
    "year": 2020
  }
}
```

**POST /tools/get-history**
```json
Request:
{
  "customer_id": "cust_001"
}

Response:
{
  "history": [
    {
      "date": "2024-10-15",
      "service_type": "oil_change",
      "cost": 59.99,
      "mileage": 45000
    }
  ]
}
```

**POST /tools/check-availability**
```json
Request:
{
  "service_type": "oil_change",
  "preferred_date": "2024-11-26"
}

Response:
{
  "available": true,
  "slots": [
    {
      "date": "2024-11-26",
      "time": "09:00",
      "duration_minutes": 30
    }
  ]
}
```

**POST /tools/schedule-appointment**
```json
Request:
{
  "customer_id": "cust_001",
  "customer_phone": "+1234567890",
  "datetime": "2024-11-26T09:00:00Z",
  "service_type": "oil_change"
}

Response:
{
  "success": true,
  "appointment_id": "apt_12345",
  "confirmation": "Scheduled oil_change for Tuesday, November 26 at 09:00 AM"
}
```

**GET /health**
```json
{
  "status": "healthy"
}
```

---

## Configuration

### Guardrails

In `layers/orchestrator.py`:

```python
# Prohibited content
prohibited_phrases = [
    "guaranteed outcome",
    "diagnose without inspection",
    "insurance fraud"
]

# Escalation triggers
escalation_keywords = [
    "lawyer", "attorney", "sue",
    "manager", "supervisor",
    "unacceptable", "furious"
]
```

### Voice Settings

In `.env`:
```bash
OPENAI_VOICE=alloy  # Options: alloy, echo, fable, onyx, nova, shimmer
```

### Turn Detection

In `layers/voice_interface.py`:
```python
"turn_detection": {
    "type": "server_vad",
    "threshold": 0.5,
    "silence_duration_ms": 500
}
```

---

## Database Schema

### Customers Table
```sql
CREATE TABLE customers (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    phone VARCHAR UNIQUE NOT NULL,
    email VARCHAR,
    vehicle_make VARCHAR,
    vehicle_model VARCHAR,
    vehicle_year INT,
    vehicle_vin VARCHAR,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Service Records Table
```sql
CREATE TABLE service_records (
    id VARCHAR PRIMARY KEY,
    customer_id VARCHAR REFERENCES customers(id),
    date DATE NOT NULL,
    service_type VARCHAR NOT NULL,
    cost DECIMAL(10,2),
    mileage INT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Appointments Table
```sql
CREATE TABLE appointments (
    id VARCHAR PRIMARY KEY,
    customer_id VARCHAR REFERENCES customers(id),
    datetime TIMESTAMP NOT NULL,
    service_type VARCHAR NOT NULL,
    duration_minutes INT DEFAULT 30,
    status VARCHAR DEFAULT 'scheduled',
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## Testing

### Run Tests
```bash
pytest tests/
```

### Manual Testing

Test tool endpoints:
```bash
curl -X POST https://your-domain.com/tools/get-customer \
  -H "Content-Type: application/json" \
  -d '{"phone": "+1234567890"}'
```

---

## Monitoring

### Logging

All logs include `call_sid` for tracing:
```
2024-11-23 10:30:00 - INFO - [CA1234] Incoming call from +1234567890
2024-11-23 10:30:05 - INFO - [CA1234] Customer: I need an oil change
2024-11-23 10:30:06 - INFO - [CA1234] Tool called: get_customer_by_phone
2024-11-23 10:30:06 - INFO - [CA1234] Tool called: check_availability
2024-11-23 10:30:07 - INFO - [CA1234] Agent: We have Tuesday at 9 AM...
```

### Metrics to Track

- Call volume
- Average call duration
- Successful bookings
- Escalation rate
- Tool execution times
- Agent response latency
- Error rate

---

## Deployment

### Production Checklist

- [ ] Set all environment variables
- [ ] Configure database
- [ ] Set up HTTPS with SSL certificate
- [ ] Configure Twilio webhooks
- [ ] Register tools in Agent Workflow
- [ ] Enable monitoring
- [ ] Set up error alerting
- [ ] Test with real calls

---

## Troubleshooting

### No Audio Heard

**Check:**
1. WebSocket connection established?
2. Audio conversion working? (mulaw ↔ PCM16)
3. OpenAI Realtime connected?

**Fix:**
```bash
# Check logs
tail -f logs/app.log | grep "CA"

# Test tool endpoint
curl -X POST https://your-domain.com/tools/get-customer \
  -H "Content-Type: application/json" \
  -d '{"phone": "+1234567890"}'
```

---

## License

MIT License

---

## Support

- **Documentation:** See documentation files
- **Issues:** GitHub Issues

---

**Built with ❤️ for better customer service**