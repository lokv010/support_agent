# OpenAI Assistant with MCP Tools Setup Guide

This guide explains how to set up and use the OpenAI Assistant API with MCP (Model Context Protocol) tools, specifically Zapier integration.

## Overview

The system now uses:
- **OpenAI Assistant API** (instead of Agents SDK) for the brain
- **MCP Server** for tool execution (Zapier)
- **OpenAI Realtime API** for voice (STT/TTS)
- **Twilio** for phone calls

### Architecture Flow

```
Customer Call (Twilio)
    ↓
WebSocket Stream
    ↓
OpenAI Realtime API (STT - Speech to Text)
    ↓
Transcription
    ↓
OpenAI Assistant API + MCP Tools (Brain)
    ├─ Understands intent
    ├─ Calls MCP tools (Zapier actions)
    └─ Generates response
    ↓
OpenAI Realtime API (TTS - Text to Speech)
    ↓
Audio Stream back to Twilio
    ↓
Customer hears response
```

## Prerequisites

1. **Python 3.10+** (installed ✓)
2. **Node.js 18+** (installed ✓)
3. **OpenAI API Key** (required)
4. **Zapier API Key** (required for MCP tools)
5. **Twilio Account** (for phone calls)

## Setup Instructions

### 1. Environment Variables

Create or update your `.env` file with the following:

```bash
# Twilio
TWILIO_ACCOUNT_SID=ACxxxxx
TWILIO_AUTH_TOKEN=your_token
TWILIO_PHONE_NUMBER=+1234567890
WEBHOOK_URL=https://your-domain.com

# OpenAI
OPENAI_API_KEY=sk-xxxxx

# Zapier (for MCP tools)
ZAPIER_API_KEY=your_zapier_api_key

# Server
PORT=5000
```

### 2. Get Your Zapier API Key

1. Go to https://zapier.com/app/login
2. Navigate to Settings → APIs
3. Create a new API key or use existing one
4. Copy the key and add it to your `.env` file

### 3. Install Dependencies

Dependencies are already installed. If you need to reinstall:

```bash
pip install -r requirements.txt
```

### 4. Test the MCP Connection

Run the test script to verify everything works:

```bash
python test_connection.py
```

Expected output:
```
======================================================================
TESTING MCP CONNECTION AND ASSISTANT SETUP
======================================================================
Initializing MCP server connection...
✓ MCP server connected
✓ Found X tools from MCP server
  - tool_name_1: Description
  - tool_name_2: Description
✓ Created Assistant: asst_xxxxx
✓ Assistant initialized with MCP tools

======================================================================
✓ MCP CONNECTION SUCCESSFUL
======================================================================

✓ Created test thread: thread_xxxxx

======================================================================
TESTING CONVERSATION
======================================================================

[TEST_CALL_123] → Assistant: Hello, can you help me?
[TEST_CALL_123] Run status: in_progress
[TEST_CALL_123] Run status: completed
[TEST_CALL_123] ← Assistant: [Response from assistant]

✓ Response received: [Response text]

======================================================================
✓ ALL TESTS PASSED
======================================================================
```

### 5. Run the Application

Start the voice agent server:

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

### 6. Configure Twilio

1. Expose your local server using ngrok or deploy to a public server:
   ```bash
   ngrok http 5000
   ```

2. In Twilio Console:
   - Go to Phone Numbers → Your Number
   - Set Voice Webhook: `https://your-domain.com/voice`
   - Set to HTTP POST
   - Save

### 7. Test the Complete Flow

1. Call your Twilio number
2. Speak to the assistant
3. The flow should be:
   - You speak → Twilio captures audio
   - Audio → OpenAI Realtime (STT)
   - Text → OpenAI Assistant (with MCP tools)
   - Assistant responds (may use Zapier tools)
   - Response → OpenAI Realtime (TTS)
   - Audio → Back to you via Twilio

## How It Works

### workflow_client.py

The new `WorkflowClient` class:

1. **Initialization** (`initialize()`)
   - Connects to MCP server (Zapier)
   - Retrieves available tools from MCP
   - Converts MCP tools to OpenAI function format
   - Creates OpenAI Assistant with tools

2. **Thread Management** (`create_thread()`)
   - Creates conversation thread per call
   - Tracks threads by call SID

3. **Message Handling** (`send_message()`)
   - Sends customer message to Assistant
   - Runs Assistant (may trigger tool calls)
   - Waits for completion
   - Returns response text

4. **Tool Execution** (`_handle_tool_calls()`)
   - Executes tools via MCP server
   - Submits results back to Assistant
   - Continues conversation flow

### MCP Configuration

The `mcp_config.json` defines the MCP server:

```json
{
  "mcpServers": {
    "zapier": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-zapier"],
      "env": {
        "ZAPIER_API_KEY": "${ZAPIER_API_KEY}"
      }
    }
  }
}
```

## Available Zapier Tools

Depending on your Zapier setup, you may have tools for:

- **Send Email** (Gmail, Outlook, etc.)
- **Send SMS** (Twilio SMS, etc.)
- **Create Calendar Event** (Google Calendar, etc.)
- **Update CRM** (Salesforce, HubSpot, etc.)
- **Send Notification** (Slack, Discord, etc.)
- **Create Task** (Asana, Trello, etc.)
- **And many more...**

To configure Zapier actions:
1. Go to https://zapier.com
2. Create Zaps for actions you want
3. Enable API access
4. Tools will automatically be available via MCP

## Troubleshooting

### No Audio from System

Check the following:

1. **OpenAI API Key**: Verify it's valid and has Realtime API access
   ```bash
   # Test in Python
   from openai import OpenAI
   client = OpenAI(api_key="your_key")
   print(client.models.list())
   ```

2. **WebSocket Connection**: Check server logs for WebSocket errors
   - Look for `[call_sid] Connected to OpenAI Realtime`
   - Look for `[call_sid] Media stream started`

3. **Twilio Configuration**: Ensure webhook URL is correct and accessible
   - Test with: `curl https://your-domain.com/health`
   - Should return: `{"status": "healthy"}`

4. **Audio Format**: The system uses:
   - Twilio: mulaw @ 8kHz
   - OpenAI: PCM16 @ 24kHz
   - Conversion is automatic

5. **Firewall/Network**: Ensure ports are open:
   - HTTP: 5000 (or your PORT)
   - WebSocket: Same port as HTTP

### MCP Connection Issues

1. **Zapier API Key**: Verify it's valid
   - Check https://zapier.com/app/settings/apis

2. **Node.js/npx**: Ensure they're installed
   ```bash
   node --version  # Should be v18+
   npx --version
   ```

3. **MCP Server Logs**: Check initialization logs
   - Should see: `✓ MCP server connected`
   - Should see: `✓ Found X tools from MCP server`

### Assistant Not Responding

1. **Check logs** for error messages with `[call_sid]` prefix

2. **Test Assistant directly**:
   ```bash
   python test_connection.py
   ```

3. **Verify OpenAI API Key** has Assistant API access

4. **Check Assistant Instructions**: May need to adjust in `workflow_client.py:96`

## Customization

### Modify Assistant Instructions

Edit `workflow_client.py` line 101-122 to customize:

```python
instructions="""You are a helpful customer support assistant with access to Zapier automation tools.

Your role is to:
- [Add your custom instructions here]
...
"""
```

### Add More MCP Servers

Edit `mcp_config.json` to add more servers:

```json
{
  "mcpServers": {
    "zapier": { ... },
    "another-server": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-another"],
      "env": { ... }
    }
  }
}
```

### Change OpenAI Model

Edit `workflow_client.py` line 123 to change model:

```python
model="gpt-4o-2024-11-20",  # Or another model
```

## Cost Considerations

- **OpenAI Realtime API**: ~$0.06/minute for audio
- **OpenAI Assistant API**: ~$0.01-0.03 per message (depending on model)
- **Twilio**: ~$0.013/minute for calls
- **Zapier**: Depends on your plan

**Estimated cost per call**: ~$0.10-0.20 per minute

## Security

1. **Never commit `.env` file** to version control
2. **Use environment variables** in production
3. **Validate Twilio webhooks** (add signature validation)
4. **Limit tool access** in Zapier (only enable needed actions)
5. **Monitor API usage** to prevent abuse

## Next Steps

1. ✓ Set up environment variables
2. ✓ Test MCP connection (`python test_connection.py`)
3. ✓ Start the server (`python app.py`)
4. Configure Twilio webhook
5. Test with a phone call
6. Configure Zapier actions
7. Deploy to production

## Support

For issues:
- Check logs with `[call_sid]` prefix
- Run test script: `python test_connection.py`
- Verify all environment variables are set
- Check Twilio webhook configuration
- Verify OpenAI API key and Zapier API key

---

**Keep it simple! 🚀**
