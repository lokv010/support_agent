# CLAUDE CODE: BUILD THIS (SIMPLE VERSION)

## Project: Voice Agent System

Connect phone calls to your Agent Workflow via voice.

---

## What to Build

**6 files total:**

```
voice-agent/
├── app.py                  # Flask + WebSocket (~50 lines)
├── voice_handler.py        # OpenAI Realtime (~150 lines)
├── workflow_client.py      # OpenAI SDK (~80 lines)
├── utils.py               # Audio conversion (~30 lines)
├── requirements.txt        # Dependencies
└── README.md              # Docs
```


---

## Simple Flow

```
Customer speaks
    ↓
OpenAI Realtime (STT - Speech to Text)
    ↓
Agent Workflow via OpenAI SDK (brain - does everything)
    ↓
OpenAI Realtime (TTS - Text to Speech)
    ↓
Customer hears
```

---

## Read This

**Complete spec:** `DEV_INSTRUCTIONS_SIMPLE.md`

Follow it step-by-step:
- STEP 1: Setup (requirements.txt, .env)
- STEP 2: utils.py (audio conversion)
- STEP 3: workflow_client.py (OpenAI SDK workflow integration)
- STEP 4: voice_handler.py (OpenAI Realtime)
- STEP 5: app.py (Flask + WebSocket)
- STEP 6: README.md

---

## Key Points

### 1. NO Tool Endpoints
The Agent Workflow is already published with all business logic.
You're just connecting voice to it.

### 2. Use OpenAI SDK
```python
from openai import OpenAI

client = OpenAI()
thread = client.beta.threads.create()
client.beta.threads.messages.create(thread_id, ...)
run = client.beta.threads.runs.create_and_poll(thread_id, assistant_id)
```

### 3. Simple Integration
```python
# Voice handler gets transcription
transcript = "I need an oil change"

# Send to workflow
response = workflow_client.send_message(call_sid, transcript)

# Workflow returns final answer
# "We have Tuesday at 9 AM or Thursday at 2 PM"

# Voice handler speaks it
```

---

## Critical Implementation

### workflow_client.py
```python
class WorkflowClient:
    def send_message(self, call_sid, text):
        # Add message to thread
        self.client.beta.threads.messages.create(
            thread_id=self.threads[call_sid],
            role="user",
            content=text
        )
        
        # Run workflow
        run = self.client.beta.threads.runs.create_and_poll(
            thread_id=self.threads[call_sid],
            assistant_id=self.workflow_id
        )
        
        # Return response
        messages = self.client.beta.threads.messages.list(...)
        return messages.data[0].content[0].text.value
```

### voice_handler.py
```python
# When customer speaks:
if event_type == 'conversation.item.input_audio_transcription.completed':
    transcript = data.get('transcript')
    
    # Send to workflow
    response_text = self.workflow_client.send_message(call_sid, transcript)
    
    # Tell OpenAI Realtime to speak it
    await openai_ws.send({
        "type": "response.create",
        "response": {
            "instructions": f"Say this: {response_text}"
        }
    })
```

---

## Success Criteria

After building:
- ✅ All 6 files created
- ✅ Flask app runs
- ✅ WebSocket connects
- ✅ OpenAI Realtime integration works
- ✅ Workflow integration works (OpenAI SDK)
- ✅ Audio conversion works
- ✅ End-to-end call works

---

## What NOT to Build

- ❌ Tool API endpoints
- ❌ Database code
- ❌ Context enrichment logic
- ❌ Manual tool execution
- ❌ CRM integrations

**Why?** Your Agent Workflow already has all of this!

---

## Start Building

1. Read `DEV_INSTRUCTIONS_SIMPLE.md` completely
2. Create project structure
3. Implement step-by-step
4. Keep it simple - exactly as spec'd
5. Don't add complexity


---

## The Rule

**If you're writing more than 300 lines of code, you're doing it wrong.**

This is a simple voice interface to your Agent Workflow.
Nothing more, nothing less.

---

**Let's keep it simple! 🚀**