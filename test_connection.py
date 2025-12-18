"""
Test script to verify MCP connection and Assistant setup
"""

import asyncio
import os
from dotenv import load_dotenv
from workflow_client import WorkflowClient

# Load environment
load_dotenv()


async def test_connection():
    """Test MCP connection and Assistant creation"""
    print("=" * 70)
    print("TESTING MCP CONNECTION AND ASSISTANT SETUP")
    print("=" * 70)

    # Initialize workflow client
    client = WorkflowClient()

    try:
        # Initialize (connects to MCP and creates Assistant)
        await client.initialize()

        print("\n" + "=" * 70)
        print("✓ MCP CONNECTION SUCCESSFUL")
        print("=" * 70)

        # Test creating a thread
        test_call_sid = "TEST_CALL_123"
        thread_id = await client.create_thread(test_call_sid)
        print(f"\n✓ Created test thread: {thread_id}")

        # Test sending a message
        print("\n" + "=" * 70)
        print("TESTING CONVERSATION")
        print("=" * 70)

        response = await client.send_message(test_call_sid, "Hello, can you help me?")
        print(f"\n✓ Response received: {response}")

        # Cleanup
        client.cleanup(test_call_sid)
        await client.shutdown()

        print("\n" + "=" * 70)
        print("✓ ALL TESTS PASSED")
        print("=" * 70)

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_connection())
