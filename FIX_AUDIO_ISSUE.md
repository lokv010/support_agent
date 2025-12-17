# Fix: Cannot Hear Audio from OpenAI Realtime

## Issue

The agent audio is not playing because the code is using a **Workflow ID** (`wf_...`) instead of an **Assistant ID** (`asst_...`).

### Error Message
```
Agent audio error: Error code: 400 - {'error': {'message': "Invalid 'assistant_id': 'wf_6927382698648190a48b3a3f4b06b6e2098fcf2a54435b0e'. Expected an ID that begins with 'asst'.", 'type': 'invalid_request_error', 'param': 'assistant_id', 'code': 'invalid_value'}}
```

## Root Cause

The `AGENT_WORKFLOW_ID` environment variable contains a workflow ID, but the code uses the OpenAI Assistants API which requires an assistant ID:

**File:** `workflow_client.py:71`
```python
run = await asyncio.to_thread(
    self.client.beta.threads.runs.create_and_poll,
    thread_id=thread_id,
    assistant_id=self.workflow_id  # ← Expects assistant ID (asst_...), not workflow ID (wf_...)
)
```

## Solution

### Step 1: Create an OpenAI Assistant

1. Go to [OpenAI Platform](https://platform.openai.com)
2. Navigate to **Dashboard** → **Assistants**
3. Click **Create Assistant**
4. Configure your assistant:
   - **Name**: Support Agent
   - **Instructions**: Add your support agent instructions (e.g., "You are a helpful customer support agent...")
   - **Model**: `gpt-4o` or `gpt-4-turbo`
   - **Tools**: Add any tools you need (file_search, code_interpreter, function calling, etc.)
5. Click **Save**
6. Copy the **Assistant ID** (it will start with `asst_`)

### Step 2: Update Environment Variable

Create or update your `.env` file with the assistant ID:

```bash
# OpenAI
OPENAI_API_KEY=your_openai_api_key

# Assistant (NOT workflow!)
AGENT_WORKFLOW_ID=asst_your_assistant_id_here  # ← Must start with 'asst'

# Twilio
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_PHONE_NUMBER=your_twilio_number
WEBHOOK_URL=your_webhook_url

# Server
PORT=5000
```

### Step 3: Restart the Server

```bash
python app.py
```

## Alternative: Rename Environment Variable

To make the code clearer, consider renaming `AGENT_WORKFLOW_ID` to `ASSISTANT_ID`:

1. Update `.env`:
   ```bash
   ASSISTANT_ID=asst_your_assistant_id_here
   ```

2. Update `workflow_client.py:16`:
   ```python
   self.assistant_id = os.getenv('ASSISTANT_ID')
   ```

3. Update `workflow_client.py:71`:
   ```python
   assistant_id=self.assistant_id
   ```

4. Update `.env.example` and documentation

## Verification

After making these changes, test the call:

1. Call your Twilio number
2. Check the logs for:
   ```
   [CALL_SID] Connected to OpenAI Realtime
   [CALL_SID] Created thread: thread_xxxxx
   [CALL_SID] Customer said: [your message]
   [CALL_SID] → Workflow: [your message]
   [CALL_SID] ← Workflow: [assistant response]
   ```
3. Verify you can **hear the assistant's voice response**

## References

- [Agent Builder Documentation](https://community.openai.com/t/agents-sdk-and-workflow-id-usage/1363213)
- [OpenAI Assistants API](https://platform.openai.com/docs/api-reference/assistants)
- [Calling AgentKit Workflow via API](https://community.openai.com/t/calling-an-agentkit-workflow-via-api-possible/1363192)

---

**Note:** Workflows (IDs starting with `wf_`) are created in Agent Builder and cannot be used directly with the Assistants API. You must use an Assistant (ID starting with `asst_`) for this integration to work.
