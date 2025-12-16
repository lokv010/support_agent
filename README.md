# Voice Agent System

Simple voice AI system connecting:
- Twilio (phone calls)
- OpenAI Realtime (voice)
- OpenAI Agent Workflow (brain)

## Overview

This system enables natural voice conversations between customers and an AI assistant for:
- Scheduling service appointments
- Checking service history
- Getting appointment availability
- Any other business logic your Agent Workflow handles

### Architecture

```
Customer speaks
    ↓
OpenAI Realtime (STT - Speech to Text)
    ↓
Agent Workflow (OpenAI SDK - thinks, decides, acts)
    ↓
OpenAI Realtime (TTS - Text to Speech)
    ↓
Customer hears
```

**Key Design Principle:** Your code = thin voice interface. Agent Workflow = smart brain.

## What This Code Does

This is a **simple voice interface** to your Agent Workflow. It:
- ✅ Connects Twilio phone calls to OpenAI Realtime
- ✅ Streams audio bidirectionally
- ✅ Converts transcriptions to workflow messages
- ✅ Speaks workflow responses

## What This Code Does NOT Do

- ❌ Business logic (your workflow handles this)
- ❌ Context enrichment (your workflow handles this)
- ❌ Tool execution (your workflow handles this)
- ❌ Database operations (your workflow calls tools for this)

**Total: ~300 lines of code**

---

## Prerequisites

- Python 3.10+
- Twilio account
- OpenAI API key
- Published OpenAI Agent Workflow (with your business logic)
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

# Agent Workflow
AGENT_WORKFLOW_ID=workflow_xxxxx  # Your published workflow ID

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
Workflow ID: workflow_xxxxx
======================================================================
Starting server on port 5000...
```

### 4. Configure Twilio

In Twilio Console:
1. Go to Phone Numbers → Your Number
2. Set Voice Webhook: `https://your-domain.com/voice`
3. Set to HTTP POST
4. Save

### 5. Test

Call your Twilio number and speak!

Your Agent Workflow handles everything:
- Understanding what you said
- Fetching any context it needs
- Executing actions
- Generating responses

---

## Project Structure

```
voice-agent/
├── app.py                  # Flask + WebSocket (~50 lines)
├── voice_handler.py        # OpenAI Realtime (~150 lines)
├── workflow_client.py      # OpenAI SDK (~80 lines)
├── utils.py               # Audio conversion (~30 lines)
├── requirements.txt        # Dependencies
├── .env.example           # Environment template
└── README.md              # This file
```

**Total: ~300 lines of code**

## Files

- `app.py` - Flask app + WebSocket handler
- `voice_handler.py` - OpenAI Realtime integration for voice
- `workflow_client.py` - Agent Workflow integration via OpenAI SDK
- `utils.py` - Audio format conversion (mulaw ↔ PCM16)

---

## How It Works

### Simple Flow

```python
# Customer speaks: "I need an oil change"

# 1. OpenAI Realtime transcribes
transcript = "I need an oil change"

# 2. Send to Agent Workflow
response = workflow_client.send_message(call_sid, transcript)
# Workflow does EVERYTHING:
#   - Understands intent
#   - Looks up customer (if needed)
#   - Checks availability (if needed)
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
   - Send to workflow via OpenAI SDK
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

This is a simple voice interface to your Agent Workflow. Nothing more, nothing less.

Your Agent Workflow already has:
- ✅ All business logic
- ✅ All tools
- ✅ All data access
- ✅ All intelligence

You just need to connect voice to it.

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

**Workflow not responding:**
- Verify `AGENT_WORKFLOW_ID` is correct
- Check OpenAI API key has access to workflows
- Look for errors in logs with `[call_sid]` prefix

---

## License

MIT

---

**Keep it simple! 🚀**