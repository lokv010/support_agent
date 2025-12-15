# CLAUDE CODE: BUILD THIS PROJECT

## Project: Car Service Voice AI System

Build a Python voice system integrating:
- **Twilio** (phone calls)
- **OpenAI Realtime API** (voice ↔ text)
- **OpenAI Agent Workflow** (business brain - already published)

---

## Instructions

**Read and follow:** `DEV_INSTRUCTIONS_UPDATED.md` (complete implementation spec)

**Reference:** `README.md` (project overview)

---

## Key Architecture Principles

### 1. Your Code is THIN
```
Voice Layer: Audio ↔ Text ONLY (~150 lines)
Orchestrator: Just routing (~50 lines)
Workflow Client: HTTP client (~20 lines)
Tool APIs: Simple endpoints (~200 lines)

Total: ~500 lines of simple code
```

### 2. Agent Workflow is SMART
```
Agent Workflow (OpenAI handles):
- Understands intent
- Fetches context (calls YOUR tools)
- Executes operations (calls YOUR tools)
- Multi-step reasoning
- Returns final response
```

### 3. NO Manual Work
```
❌ DON'T manually enrich context
❌ DON'T manually execute tools
❌ DON'T manually orchestrate workflows

✅ DO call Agent Workflow API
✅ DO provide tool endpoints
✅ DO route messages
```

---

## Build Order

Follow DEV_INSTRUCTIONS_UPDATED.md steps:

1. **STEP 1:** Project setup (structure, requirements.txt, .env.example)
2. **STEP 2:** Utilities (audio.py, logger.py)
3. **STEP 3:** Data models (session.py, customer.py, appointment.py)
4. **STEP 4:** Voice interface layer (OpenAI Realtime)
5. **STEP 5:** Workflow client (simple HTTP)
6. **STEP 6:** Orchestrator (routing)
7. **STEP 7:** Tool APIs (4 endpoints)
8. **STEP 8:** Main app.py
9. **STEP 9:** Agent Workflow config docs
10. **STEP 10:** Tests

---

## Critical Implementation Notes

### Voice Layer (STEP 4)
```python
class VoiceInterfaceHandler:
    config = {
        "tools": [],  # NO business tools!
        "instructions": "You are a voice interface. NO business decisions."
    }
```

### Orchestrator (STEP 6)
```python
async def handle_transcription(call_sid, text):
    # Apply guardrails
    # Send to workflow (no context enrichment!)
    result = await workflow_client.send_message(
        conversation_id,
        text,
        customer_phone  # Just identifier!
    )
    # Send to voice layer
```

### Workflow Client (STEP 5)
```python
async def send_message(conversation_id, message, customer_phone):
    # ONE HTTP call, get final response
    response = await http_post(
        f"{workflow_url}/messages",
        json={"message": message, "customer_phone": customer_phone}
    )
    return response["response"]  # Tools already executed!
```

### Tool APIs (STEP 7)
```python
# Agent Workflow CALLS these

@app.route('/tools/get-customer', methods=['POST'])
async def get_customer():
    phone = request.json['phone']
    customer = await lookup(phone)
    return jsonify(customer.to_dict())

@app.route('/tools/get-history', methods=['POST'])
async def get_history():
    customer_id = request.json['customer_id']
    history = await get_history(customer_id)
    return jsonify({"history": history})

# + check-availability, schedule-appointment
```

---

## Expected Output

After building, the project should have:

```
car-service-voice-system/
├── README.md
├── requirements.txt
├── .env.example
├── app.py                          # Flask + WebSocket
├── layers/
│   ├── voice_interface.py          # ~150 lines
│   ├── orchestrator.py             # ~50 lines
│   └── workflow_client.py          # ~20 lines
├── models/
│   ├── session.py
├── utils/
│   ├── logger.py
│   └── audio.py
└── tests/
    ├── test_voice.py
    ├── test_orchestrator.py
    └── test_tools.py
```

---

## Success Criteria

- ✅ All files created per DEV_INSTRUCTIONS_UPDATED.md
- ✅ Voice layer: NO business tools in config
- ✅ Orchestrator: NO context enrichment logic
- ✅ Workflow client: Simple HTTP calls only
- ✅ Tool APIs: 4 endpoints implemented
- ✅ app.py: Flask + WebSocket working
- ✅ Tests: Basic test structure
- ✅ Type hints throughout
- ✅ Comprehensive logging with call_sid

---

## Start Here

1. Create project structure (STEP 1)
2. Read each STEP in DEV_INSTRUCTIONS_UPDATED.md
3. Implement each file as specified
4. Keep it SIMPLE - no extra complexity
5. Follow the principle: Your code is thin, Agent Workflow is smart

**Estimated time: 1 day**

---

## Questions?

Refer to:
- **DEV_INSTRUCTIONS_UPDATED.md** - Complete spec (~8,000 lines)
- **README.md** - Project overview (~1,500 lines)
- **ULTRA_SIMPLIFIED_ARCHITECTURE.md** - Architecture deep-dive
- **CORRECTED_BUSINESS_LOGIC.md** - Why this design

All questions should be answered in these docs.

---

**Let's build! 🚀**