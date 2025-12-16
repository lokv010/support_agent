"""Configuration settings for the car service voice AI system."""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Application configuration from environment variables."""

    # Twilio Configuration
    TWILIO_ACCOUNT_SID: str = os.getenv('TWILIO_ACCOUNT_SID', '')
    TWILIO_AUTH_TOKEN: str = os.getenv('TWILIO_AUTH_TOKEN', '')
    TWILIO_PHONE_NUMBER: str = os.getenv('TWILIO_PHONE_NUMBER', '')
    WEBHOOK_URL: str = os.getenv('WEBHOOK_URL', '')

    # OpenAI Configuration
    OPENAI_API_KEY: str = os.getenv('OPENAI_API_KEY', '')
    OPENAI_REALTIME_MODEL: str = os.getenv('OPENAI_REALTIME_MODEL', 'gpt-4o-realtime-preview-2024-10-01')
    OPENAI_WORKFLOW_MODEL: str = os.getenv('OPENAI_WORKFLOW_MODEL', 'gpt-4-turbo')
    OPENAI_VOICE: str = os.getenv('OPENAI_VOICE', 'alloy')

    # Agent Workflow Configuration
    AGENT_WORKFLOW_URL: str = os.getenv('AGENT_WORKFLOW_URL', '')
    AGENT_WORKFLOW_API_KEY: str = os.getenv('AGENT_WORKFLOW_API_KEY', '')

    # Server Configuration
    FLASK_PORT: int = int(os.getenv('FLASK_PORT', '5000'))
    WEBSOCKET_PORT: int = int(os.getenv('WEBSOCKET_PORT', '8080'))
    WEBSOCKET_HOST: str = os.getenv('WEBSOCKET_HOST', '0.0.0.0')

    # Database Configuration
    DATABASE_URL: str = os.getenv('DATABASE_URL', '')

    # Logging Configuration
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE: str = os.getenv('LOG_FILE', 'logs/app.log')

    # Business Rules
    MAX_CONVERSATION_TURNS: int = int(os.getenv('MAX_CONVERSATION_TURNS', '25'))
    MAX_TURN_DURATION_SECONDS: int = int(os.getenv('MAX_TURN_DURATION_SECONDS', '35'))
    SESSION_TIMEOUT_MINUTES: int = int(os.getenv('SESSION_TIMEOUT_MINUTES', '30'))

    @classmethod
    def validate(cls) -> bool:
        """Validate that all required configuration is set."""
        required_fields = [
            'TWILIO_ACCOUNT_SID',
            'TWILIO_AUTH_TOKEN',
            'TWILIO_PHONE_NUMBER',
            'OPENAI_API_KEY',
            'AGENT_WORKFLOW_URL'
        ]

        missing = []
        for field in required_fields:
            value = getattr(cls, field, '')
            if not value:
                missing.append(field)

        if missing:
            print(f"ERROR: Missing required configuration: {', '.join(missing)}")
            return False

        return True

    @classmethod
    def to_dict(cls) -> dict:
        """Convert configuration to dictionary (excluding sensitive data)."""
        return {
            'OPENAI_REALTIME_MODEL': cls.OPENAI_REALTIME_MODEL,
            'OPENAI_WORKFLOW_MODEL': cls.OPENAI_WORKFLOW_MODEL,
            'OPENAI_VOICE': cls.OPENAI_VOICE,
            'FLASK_PORT': cls.FLASK_PORT,
            'WEBSOCKET_PORT': cls.WEBSOCKET_PORT,
            'LOG_LEVEL': cls.LOG_LEVEL,
            'MAX_CONVERSATION_TURNS': cls.MAX_CONVERSATION_TURNS,
            'MAX_TURN_DURATION_SECONDS': cls.MAX_TURN_DURATION_SECONDS,
            'SESSION_TIMEOUT_MINUTES': cls.SESSION_TIMEOUT_MINUTES,
        }


# Global config instance
config = Config()
