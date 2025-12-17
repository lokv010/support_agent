# Voice Agent System

Simple voice AI system connecting:
- Twilio (phone calls)
- OpenAI Realtime (voice)
- OpenAI Agents SDK (brain)

## Overview

This system enables natural voice conversations between customers and an AI assistant for:
- Scheduling service appointments
- Checking service history
- Getting appointment availability
- Any other business logic your Agent handles

### Architecture

```
Customer speaks
    ↓
OpenAI Realtime (STT - Speech to Text)
    ↓
OpenAI Agents SDK (thinks, decides, acts with tools)
    ↓
OpenAI Realtime (TTS - Text to Speech)
    ↓
Customer hears
```

**Key Design Principle:** Your code = thin voice interface. OpenAI Agent = smart brain.

## What This Code Does

This is a **simple voice interface** to your OpenAI Agent. It:
- ✅ Connects Twilio phone calls to OpenAI Realtime
- ✅ Streams audio bidirectionally
- ✅ Converts transcriptions to agent messages
- ✅ Speaks agent responses

## What This Code Does NOT Do

- ❌ Business logic (your agent handles this)
- ❌ Context enrichment (your agent handles this)
- ❌ Tool execution (your agent handles this with tools)
- ❌ Database operations (your agent calls tools for this)

**Total: ~300 lines of code**

---

## Prerequisites

- Python 3.10+
- Twilio account
- OpenAI API key
- Public HTTPS endpoint (for webhooks)

---

## Setup

### 1. Install Dependencies

```bash
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

# Server
PORT=5000
```

### 3. Run the Application

```bash
python app.py
```

You should see:
```
======================================================================
VOICE AGENT SYSTEM STARTED
======================================================================
Using OpenAI Agents SDK
======================================================================
Starting server on port 5000...
```

### 4. Configure Twilio

In Twilio Console:
1. Go to Phone Numbers → Your Number
2. Set Voice Webhook: `https://your-domain.com/voice`
3. Set to HTTP POST
4. Save

### 5. Customize Your Agent

Edit `workflow_client.py` to customize your agent's behavior:

```python
self.agent = Agent(
    name="Support Assistant",
    instructions="""Your custom instructions here...""",
    # Add tools for business logic
    # tools=[check_availability, schedule_appointment]
)
```

### 6. Test

Call your Twilio number and speak!

Your Agent handles everything:
- Understanding what you said
- Calling tools if configured
- Maintaining conversation context
- Generating responses

---

## Project Structure

```
voice-agent/
├── app.py                  # Flask + WebSocket (~50 lines)
├── voice_handler.py        # OpenAI Realtime (~150 lines)
├── workflow_client.py      # OpenAI Agents SDK (~90 lines)
├── utils.py               # Audio conversion (~30 lines)
├── requirements.txt        # Dependencies
├── .env.example           # Environment template
└── README.md              # This file
```

**Total: ~300 lines of code**

## Files

- `app.py` - Flask app + WebSocket handler
- `voice_handler.py` - OpenAI Realtime integration for voice
- `workflow_client.py` - Agent integration via OpenAI Agents SDK
- `utils.py` - Audio format conversion (mulaw ↔ PCM16)

---

## How It Works

### Simple Flow

```python
# Customer speaks: "I need an oil change"

# 1. OpenAI Realtime transcribes
transcript = "I need an oil change"

# 2. Send to Agent
response = workflow_client.send_message(call_sid, transcript)
# Agent does EVERYTHING:
#   - Understands intent
#   - Calls tools if configured (e.g., check availability)
#   - Maintains conversation context
#   - Generates response

# 3. OpenAI Realtime speaks response
# Response: "We have Tuesday at 9 AM or Thursday at 2 PM"
```

**Simple!**

### Call Flow

1. Customer calls → Twilio webhook (`/voice`)
2. App returns TwiML with WebSocket stream
3. WebSocket connects (`/media-stream`)
4. Voice handler connects to OpenAI Realtime
5. Bidirectional audio streaming begins:
   - Twilio → OpenAI (customer audio)
   - OpenAI → Twilio (agent audio)
6. On transcription:
   - Send to agent via OpenAI Agents SDK
   - Agent processes (calls tools if needed)
   - Get response
   - Tell OpenAI Realtime to speak it
7. Repeat until call ends

---

## API Endpoints

### Twilio Webhooks

**POST /voice**
- Initial call webhook from Twilio
- Returns TwiML with media stream configuration

**WebSocket /media-stream**
- Bidirectional audio streaming
- Connects Twilio calls to OpenAI Realtime

**GET /health**
- Health check endpoint
- Returns: `{"status": "healthy"}`

---

## Key Principle

**If you're writing more than 300 lines of code, you're doing it wrong.**

This is a simple voice interface to your OpenAI Agent. Nothing more, nothing less.

Define your agent in `workflow_client.py` with:
- ✅ Instructions (what the agent should do)
- ✅ Tools (functions it can call)
- ✅ Session management (conversation memory)

The OpenAI Agents SDK handles the rest. You just connect voice to it.

---

## Deployment

1. Deploy to any Python hosting (Heroku, Railway, Render, etc.)
2. Set environment variables
3. Configure Twilio webhook to point to your `/voice` endpoint
4. Done!

---

## Troubleshooting

### Common Issues

**No audio heard:**
- Check WebSocket connection in logs
- Verify OpenAI API key is valid
- Ensure HTTPS is working (Twilio requires HTTPS)

**Agent not responding:**
- Check OpenAI API key is valid
- Verify agent instructions are clear
- Look for errors in logs with `[call_sid]` prefix
- Check if tools are properly configured (if using any)

---

## License

MIT

---

**Keep it simple! 🚀**