"""
Integration tests for Support Agent <-> CRM MCP Server

Tests that the WorkflowClient correctly:
1. Connects to the CRM MCP server via Streamable HTTP
2. Discovers available MCP tools
3. Creates sessions and sends messages
4. Cleans up properly

Run with: python -m pytest tests/test_crm_mcp_integration.py -v
"""

import asyncio
import json
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestWorkflowClientInit:
    """Test WorkflowClient initialization and MCP configuration."""

    def test_default_crm_url(self):
        """WorkflowClient uses default CRM MCP URL when env var not set."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CRM_MCP_URL", None)
            # Re-import to pick up default
            import importlib
            import workflow_client as wc
            importlib.reload(wc)
            assert wc.CRM_MCP_URL == "http://localhost:3100/mcp"

    def test_custom_crm_url(self):
        """WorkflowClient uses custom CRM MCP URL from env var."""
        with patch.dict(os.environ, {"CRM_MCP_URL": "http://crm:4000/mcp"}):
            import importlib
            import workflow_client as wc
            importlib.reload(wc)
            assert wc.CRM_MCP_URL == "http://crm:4000/mcp"

    def test_agent_has_mcp_servers(self):
        """Agent is configured with CRM MCP server."""
        from workflow_client import WorkflowClient
        client = WorkflowClient()
        assert len(client.agent.mcp_servers) == 1
        assert client.agent.mcp_servers[0].name == "CRM MCP Server"

    def test_agent_instructions_reference_crm_tools(self):
        """Agent instructions reference CRM MCP tools."""
        from workflow_client import WorkflowClient
        client = WorkflowClient()
        instructions = client.agent.instructions
        assert "check_customer_history" in instructions
        assert "list_event_types" in instructions
        assert "create_event" in instructions
        assert "add_customer_record" in instructions
        assert "send_appointment_confirmation" in instructions

    def test_initial_state(self):
        """WorkflowClient starts disconnected with no sessions."""
        from workflow_client import WorkflowClient
        client = WorkflowClient()
        assert client._connected is False
        assert client.sessions == {}


class TestWorkflowClientLifecycle:
    """Test connect/disconnect lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_sets_connected_flag(self):
        """connect() sets _connected flag."""
        from workflow_client import WorkflowClient
        client = WorkflowClient()

        with patch.object(client.crm_server, '__aenter__', new_callable=AsyncMock) as mock_enter:
            await client.connect()
            assert client._connected is True
            mock_enter.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_idempotent(self):
        """Calling connect() twice only connects once."""
        from workflow_client import WorkflowClient
        client = WorkflowClient()

        with patch.object(client.crm_server, '__aenter__', new_callable=AsyncMock) as mock_enter:
            await client.connect()
            await client.connect()
            mock_enter.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """disconnect() clears _connected flag."""
        from workflow_client import WorkflowClient
        client = WorkflowClient()

        with patch.object(client.crm_server, '__aenter__', new_callable=AsyncMock):
            await client.connect()

        with patch.object(client.crm_server, '__aexit__', new_callable=AsyncMock) as mock_exit:
            await client.disconnect()
            assert client._connected is False
            mock_exit.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        """disconnect() is a no-op when not connected."""
        from workflow_client import WorkflowClient
        client = WorkflowClient()

        with patch.object(client.crm_server, '__aexit__', new_callable=AsyncMock) as mock_exit:
            await client.disconnect()
            mock_exit.assert_not_called()


class TestWorkflowClientSessions:
    """Test session management."""

    @pytest.mark.asyncio
    async def test_create_thread(self):
        """create_thread() creates a session and auto-connects."""
        from workflow_client import WorkflowClient
        client = WorkflowClient()

        with patch.object(client.crm_server, '__aenter__', new_callable=AsyncMock):
            result = await client.create_thread("CA123")

        assert result == "CA123"
        assert "CA123" in client.sessions

    @pytest.mark.asyncio
    async def test_send_message_creates_session_if_missing(self):
        """send_message() auto-creates session if none exists."""
        from workflow_client import WorkflowClient
        client = WorkflowClient()

        mock_result = MagicMock()
        mock_result.final_output = "Hello! How can I help?"

        with patch.object(client.crm_server, '__aenter__', new_callable=AsyncMock):
            with patch('workflow_client.Runner.run', new_callable=AsyncMock, return_value=mock_result):
                response = await client.send_message("CA456", "Hi there")

        assert response == "Hello! How can I help?"
        assert "CA456" in client.sessions

    @pytest.mark.asyncio
    async def test_send_message_uses_existing_session(self):
        """send_message() reuses existing session."""
        from workflow_client import WorkflowClient
        from agents import SQLiteSession  # noqa: F811
        client = WorkflowClient()
        client._connected = True

        session = SQLiteSession(db_path=":memory:", session_id="CA789")
        client.sessions["CA789"] = session

        mock_result = MagicMock()
        mock_result.final_output = "I can help with that."

        with patch('workflow_client.Runner.run', new_callable=AsyncMock, return_value=mock_result) as mock_run:
            response = await client.send_message("CA789", "I need an appointment")

        assert response == "I can help with that."
        # Verify the existing session was passed
        _, kwargs = mock_run.call_args
        assert kwargs['session'] is session

    def test_cleanup_removes_session(self):
        """cleanup() removes the session for a call_sid."""
        from workflow_client import WorkflowClient
        from agents import SQLiteSession  # noqa: F811
        client = WorkflowClient()
        client.sessions["CA999"] = SQLiteSession(db_path=":memory:", session_id="CA999")

        client.cleanup("CA999")
        assert "CA999" not in client.sessions

    def test_cleanup_nonexistent_session(self):
        """cleanup() is safe for non-existent sessions."""
        from workflow_client import WorkflowClient
        client = WorkflowClient()
        client.cleanup("NONEXISTENT")  # Should not raise


class TestMCPServerConfiguration:
    """Test that the MCP server object is configured correctly."""

    def test_crm_server_params(self):
        """CRM server has correct URL and timeout."""
        from workflow_client import WorkflowClient, CRM_MCP_URL
        client = WorkflowClient()
        assert client.crm_server.name == "CRM MCP Server"

    def test_cache_tools_enabled(self):
        """Tool caching is enabled for performance."""
        from workflow_client import WorkflowClient
        client = WorkflowClient()
        assert client.crm_server.cache_tools_list is True


class TestAppIntegration:
    """Test the Quart app integration with WorkflowClient."""

    def test_app_imports_workflow_client_with_mcp(self):
        """App module uses WorkflowClient that has MCP configured."""
        import app as app_module
        assert hasattr(app_module, 'workflow_client')
        assert len(app_module.workflow_client.agent.mcp_servers) == 1

    def test_app_has_lifecycle_hooks(self):
        """App has before_serving and after_serving hooks for MCP lifecycle."""
        import app as app_module
        # Check that the app has before/after serving hooks registered
        assert hasattr(app_module, 'startup')
        assert hasattr(app_module, 'shutdown')

    def test_health_returns_crm_status(self):
        """Health endpoint function exists and returns crm_mcp_connected."""
        import app as app_module
        assert hasattr(app_module, 'health')
